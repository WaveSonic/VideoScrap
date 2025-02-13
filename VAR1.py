import cv2
import numpy as np
import threading
import queue
import time
import math
import ttkbootstrap as ttk
from tkinter import filedialog
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
import json
from datetime import datetime

# Словник для зберігання даних

is_playing = False
output_file_name = ""

def calculate_distance(x1, y1, x2, y2):
    """Обчислення евклідової відстані."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

def video_reader(source, frame_queue, stop_event):
    """Потік для зчитування відео."""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Не вдалося відкрити джерело: {source}")
        stop_event.set()
        return

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            print("Кінець відео або помилка читання кадру.")
            break

        try:
            frame_queue.put(frame, timeout=1)
        except queue.Full:
            print("Черга кадрів заповнена. Пропуск кадру.")

    cap.release()
    global is_playing
    is_playing = False
    stop_video()  # Викликаємо зупинку відео після завершення потоку

def video_processor(frame_queue, stop_event, video_label):
    """Потік для обробки відео."""
    global object_data_dict
    back_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=20, detectShadows=False)
    object_data = {}  # Зберігання даних для кожного ID
    id_counter = 0  # Лічильник для унікальних ID
    frame_count = 0

    max_width, max_height = 1020, 800
    while not stop_event.is_set() or not frame_queue.empty():
        try:
            frame = frame_queue.get(timeout=1)
        except queue.Empty:
            continue

        fg_mask = back_sub.apply(frame)
        fg_mask = cv2.medianBlur(fg_mask, 5)
        _, fg_mask = cv2.threshold(fg_mask, 50, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        current_ids = set()

        frame_height, frame_width, _ = frame.shape
        scale = min(max_width / frame_width, max_height / frame_height, 1.0)

        for contour in contours:
            if cv2.contourArea(contour) > 1000:
                x, y, w, h = cv2.boundingRect(contour)
                cx, cy = x + w // 2, y + h // 2

                # Знаходимо існуючий об'єкт або створюємо новий
                matched_id = None
                for obj_id, data in object_data.items():
                    prev_coords = data["coords"]
                    if calculate_distance(prev_coords[0], prev_coords[1], cx, cy) < 50:  # Поріг для збігу
                        matched_id = obj_id
                        break

                if matched_id is None:
                    id_counter += 1
                    matched_id = f"ID_{id_counter}"
                    object_data[matched_id] = {
                        "coords": (cx, cy),
                        "time": time.time(),
                        "distance": 0,
                        "velocity": 0,
                        "updated": True
                    }

                current_ids.add(matched_id)
                prev_coords = object_data[matched_id]["coords"]
                prev_time = object_data[matched_id]["time"]

                # Обчислення відстані та швидкості
                distance = calculate_distance(prev_coords[0], prev_coords[1], cx, cy)
                elapsed_time = time.time() - prev_time
                velocity = distance / elapsed_time if elapsed_time > 0 else 0
                updated = distance > 1

                object_data[matched_id].update({
                    "coords": (cx, cy),
                    "time": time.time(),
                    "distance": distance,
                    "velocity": velocity,
                    "updated": updated
                })

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, matched_id, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # Видалення об'єктів, які відсутні
        for obj_id in list(object_data.keys()):
            if obj_id not in current_ids:
                current_time = time.time()
                elapsed_time = current_time - object_data[obj_id]["time"]
                if elapsed_time > 1:
                    del object_data[obj_id]

        object_data_dict[frame_count] = {
            "objects": object_data.copy()
        }

        frame_height, frame_width, _ = frame.shape
        scale = min(max_width / frame_width, max_height / frame_height, 1.0)
        new_width = int(frame_width * scale)
        new_height = int(frame_height * scale)
        resized_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

        rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb_frame))
        video_label.config(image=img)
        video_label.image = img

        frame_count += 1

        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_event.set()
            break

def start_tracking(video_source, video_label, right_frame):
    global is_playing, reader_thread, processor_thread, stop_event, frame_queue, object_data_dict, output_file_name

    if is_playing:
        print("Відтворення вже запущено!")
        return

    if not video_source:
        print("Будь ласка, виберіть файл відео.")
        return

    # Генерація назви файлу для запису даних
    video_name = video_source.split('/')[-1].split('.')[0]
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file_name = f"{video_name}_{current_time}.json"

    object_data_dict = {}  # Очищення словника
    frame_queue = queue.Queue(maxsize=20)
    stop_event = threading.Event()

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print(f"Не вдалося відкрити джерело: {video_source}")
        return
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    max_width, max_height = 1020, 800
    scale = min(max_width / frame_width, max_height / frame_height, 1.0)
    new_width = int(frame_width * scale)
    new_height = int(frame_height * scale)

    right_frame.config(width=new_width, height=new_height)
    right_frame.pack_propagate(False)

    is_playing = True

    reader_thread = threading.Thread(target=video_reader, args=(video_source, frame_queue, stop_event))
    processor_thread = threading.Thread(target=video_processor, args=(frame_queue, stop_event, video_label))

    reader_thread.start()
    processor_thread.start()

def stop_video():
    """Зупинка потоків і запис даних у файл."""
    global is_playing, stop_event, reader_thread, processor_thread, frame_queue, object_data_dict, output_file_name

    if not is_playing:
        print("Відео не запущене!")
        return

    stop_event.set()

    if reader_thread.is_alive():
        reader_thread.join(timeout=1)
    if processor_thread.is_alive():
        processor_thread.join(timeout=1)

    video_label.config(image="")
    video_label.image = None

    with frame_queue.mutex:
        frame_queue.queue.clear()

    is_playing = False
    print(f"Відтворення відео зупинено та дані збережено у файл: {output_file_name}")

def select_video_file(entry):
    """Вибір відеофайлу."""
    filepath = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi;*.mkv")])
    if filepath:
        entry.delete(0, END)
        entry.insert(0, filepath)

app = ttk.Window(themename="darkly")
app.title("Відстеження об'єктів у відео")
app.geometry("1800x1000")

main_frame = ttk.Frame(app)
main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

controls_frame = ttk.Frame(main_frame)
controls_frame.pack(fill=X, pady=5)

file_entry = ttk.Entry(controls_frame, width=50)
file_entry.pack(side=LEFT, padx=5)

file_button = ttk.Button(controls_frame, text="Вибрати відео", command=lambda: select_video_file(file_entry))
file_button.pack(side=LEFT, padx=5)

start_button = ttk.Button(
    controls_frame,
    text="Запустити",
    command=lambda: start_tracking(file_entry.get(), video_label, right_frame)
)
start_button.pack(side=LEFT, padx=5)

stop_button = ttk.Button(
    controls_frame,
    text="Зупинити",
    bootstyle="danger",
    command=stop_video
)
stop_button.pack(side=LEFT, padx=5)

content_frame = ttk.Frame(main_frame)
content_frame.pack(fill=BOTH, expand=True)

left_frame = ttk.Frame(content_frame, width=800)
left_frame.pack(side=LEFT, fill=Y, padx=5, pady=5)

right_frame = ttk.Frame(content_frame, relief="sunken", borderwidth=2, width=1000, height=1000)
right_frame.pack(side=RIGHT, padx=20, pady=20)
right_frame.pack_propagate(False)

video_label = ttk.Label(right_frame)
video_label.pack(fill=BOTH, expand=True)

app.mainloop()
