import threading
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox, Toplevel, Scale, HORIZONTAL
import cv2
from PIL import Image, ImageTk
import time
import queue
import json
import os
from datetime import datetime

SETTINGS_FILE = "settings.json"
# Налаштування за замовчуванням
default_settings = {
    "history": 500,
    "varThreshold": 25,
    "min_contour_area": 1000,
    "max_disappear_time": 1.0,
    "min_visible_time": 1.0
}

settings = default_settings.copy()

if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = json.load(f)
else:
    settings = default_settings.copy()
tracked_data = {}
is_playing = False  # Статус відтворення відео
stop_event = threading.Event()  # Подія для зупинки відео
data_queue = queue.Queue()  # Черга для оновлення таблиці

def save_settings():
    """Зберігає налаштування у JSON-файл."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


def create_gui():
    def open_settings_window():
        """Відкриває вікно налаштувань."""
        settings_window = Toplevel(app)
        settings_window.title("Налаштування")
        settings_window.geometry("500x300")  # Менше вікно, оскільки параметрів менше
        settings_window.attributes('-topmost', True)  # Вікно завжди поверх

        def update_setting(key, value):
            """Оновлення параметра та збереження у файл."""
            settings[key] = value
            save_settings()

        def update_slider(event, key, slider):
            """Оновлення повзунка при введенні числа вручну."""
            try:
                value = event.widget.get().replace(",", ".")  # Замінюємо кому на крапку
                value = float(value)  # Перетворюємо в число
                value = max(slider.cget("from"), min(value, slider.cget("to")))  # Обмежуємо значення
                slider.set(value)  # Оновлюємо повзунок
                update_setting(key, value)  # Оновлюємо налаштування
            except ValueError:
                pass  # Ігноруємо некоректне введення

        def update_entry(slider, entry, key):
            """Оновлення поля введення при зміні повзунка."""
            value = round(slider.get(), 2)
            entry.delete(0, END)
            entry.insert(0, f"{value:.2f}".replace(".", ","))  # Відображаємо з комою
            update_setting(key, value)

        def create_setting_row(label_text, key, from_, to_, step, description):
            """Створює рядок з налаштуванням."""
            frame = ttk.Frame(settings_window)
            frame.pack(fill=X, padx=10, pady=5)

            ttk.Label(frame, text=label_text, width=18, anchor=W).pack(side=LEFT)  # Назва параметра
            slider = Scale(frame, from_=from_, to=to_, orient=HORIZONTAL, resolution=step,
                           command=lambda v: update_entry(slider, entry, key))
            slider.set(settings[key])
            slider.pack(side=LEFT, fill=X, expand=True, padx=5)

            entry = ttk.Entry(frame, width=6)
            entry.insert(0, f"{settings[key]:.2f}".replace(".", ","))  # Відображаємо з комою
            entry.pack(side=LEFT, padx=5)
            entry.bind("<Return>", lambda event, k=key, s=slider: update_slider(event, k, s))

            ttk.Label(frame, text=description, width=18, anchor=W).pack(side=LEFT)  # Опис

        ttk.Label(settings_window, text="Налаштування виявлення об'єктів", font=("Arial", 12, "bold")).pack(pady=5)

        # Залишаємо тільки три потрібні параметри
        create_setting_row("Довжина історії:", "history", 100, 2000, 100, "Чутливість до старих об'єктів")
        create_setting_row("Поріг руху:", "varThreshold", 10, 100, 1, "Від 10 - дуже чутливий")
        create_setting_row("Мін. площа (px²):", "min_contour_area", 500, 5000, 100, "Фільтр дрібних об'єктів")

        def reset_settings():
            """Скидає налаштування до стандартних значень."""
            global settings
            settings = default_settings.copy()
            save_settings()
            settings_window.destroy()
            open_settings_window()  # Перезапускаємо вікно
            messagebox.showinfo("Налаштування", "Налаштування скинуто до стандартних значень.")

        def save_and_close():
            """Зберігає налаштування та закриває вікно."""
            save_settings()
            messagebox.showinfo("Збереження", "Налаштування збережено успішно.")
            settings_window.destroy()

        # Кнопки управління
        btn_frame = ttk.Frame(settings_window)
        btn_frame.pack(fill=X, pady=10)

        ttk.Button(btn_frame, text="Скинути налаштування", command=reset_settings, bootstyle="danger").pack(side=LEFT,
                                                                                                            padx=10)
        ttk.Button(btn_frame, text="Зберегти", command=save_and_close, bootstyle="success").pack(side=RIGHT, padx=10)


    def save_data_to_json():
        """Зберігає tracked_data у JSON-файл."""
        if not tracked_data:
            print("Немає даних для збереження.")
            return

        # Формуємо назву файлу: назва відео + датачас
        filepath = file_entry.get()
        if not filepath:
            print("Не вдалося отримати назву відео.")
            return

        video_name = filepath.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{video_name}_{timestamp}.json"

        # Записуємо дані у файл
        with open(filename, "w", encoding="utf-8") as json_file:
            json.dump(tracked_data, json_file, indent=4, ensure_ascii=False)

        print(f"Дані збережено у файл: {filename}")

    def update_table_worker():

        """Фоновий потік для оновлення таблиці."""
        while True:  # Без перевірки stop_event
            try:
                objects, frame_count, elapsed_time = data_queue.get(timeout=1)
                table.after(0, update_table, objects, frame_count)
            except queue.Empty:
                continue

    def update_table(objects, frame_count):
        """Оновлення таблиці даними про об'єкти."""
        pixel_to_mm = 0.1  # Коефіцієнт перетворення пікселів у мм

        existing_ids = {table.item(row)["values"][0] for row in table.get_children()}

        for obj_id, data in objects.items():
            x_pixel, y_pixel = data["coords"]
            x_mm, y_mm = x_pixel * pixel_to_mm, y_pixel * pixel_to_mm

            # Обчислення переміщення (відстань від попереднього положення)
            prev_x, prev_y = data.get("prev_coords", (x_pixel, y_pixel))
            displacement = ((x_pixel - prev_x) ** 2 + (y_pixel - prev_y) ** 2) ** 0.5 * pixel_to_mm
            data["prev_coords"] = (x_pixel, y_pixel)  # Оновлюємо попередні координати

            # Середня швидкість
            average_velocity = data["total_velocity"] / data["velocity_count"] if data["velocity_count"] > 0 else 0

            if average_velocity == 0:
                continue

            # Оновити існуючий рядок або додати новий
            if obj_id in existing_ids:
                for row in table.get_children():
                    if table.item(row)["values"][0] == obj_id:
                        table.item(row, values=(
                            obj_id, frame_count,
                            round(x_mm, 3), round(y_mm, 3),
                            round(displacement, 3), round(average_velocity, 3)
                        ))
                        break
            else:
                table.insert("", "end", values=(
                    obj_id, frame_count,
                    round(x_mm, 3), round(y_mm, 3),
                    round(displacement, 3), round(average_velocity, 3)
                ))
            if obj_id not in tracked_data:
                tracked_data[obj_id] = []
            tracked_data[obj_id].append({
                "frame": frame_count,
                "x_mm": round(x_mm, 3),
                "y_mm": round(y_mm, 3),
                "displacement_mm": round(displacement, 3),
                "average_velocity_mm_s": round(average_velocity, 3)
            })

    def select_video():
        """Обробка вибору відеофайлу."""
        filepath = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi;*.mkv")])
        if filepath:
            file_entry.delete(0, END)
            file_entry.insert(0, filepath)

    def start_video():
        """Запуск відео в окремому потоці."""
        global is_playing, stop_event, tracked_data
        if is_playing:
            print("Відео вже запущено!")
            return

        filepath = file_entry.get()
        if not filepath:
            print("Будь ласка, виберіть файл відео.")
            return

        for row in table.get_children():
            table.delete(row)


        tracked_data = {}


        def play_video():
            global is_playing
            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                print(f"Не вдалося відкрити відео: {filepath}")
                is_playing = False
                return

            stop_event.clear()
            is_playing = True

            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30
            frame_delay = 1 / fps

            back_sub = cv2.createBackgroundSubtractorMOG2(
                history=int(settings["history"]),
                varThreshold=int(settings["varThreshold"]),
                detectShadows=True
            )
            display_width = right_frame.winfo_width()
            display_height = right_frame.winfo_height()

            object_data = {}
            object_id_counter = -1
            max_disappear_time = 1.0
            min_visible_time = 1.0

            last_frame_time = time.time()
            prev_img = None
            frame_count = 0
            while cap.isOpened() and not stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    print("Відтворення завершено або помилка читання відео.")
                    break

                fg_mask = back_sub.apply(frame)
                _, fg_mask = cv2.threshold(fg_mask, 50, 255, cv2.THRESH_BINARY)
                fg_mask = cv2.medianBlur(fg_mask, 5)

                contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                current_objects = {}

                current_time = time.time()
                start_time = time.time()

                for contour in contours:
                    if cv2.contourArea(contour) > 1000:
                        x, y, w, h = cv2.boundingRect(contour)
                        cx, cy = x + w // 2, y + h // 2

                        matched_id = None
                        for obj_id, data in object_data.items():
                            prev_coords = data["coords"]
                            if ((cx - prev_coords[0]) ** 2 + (cy - prev_coords[1]) ** 2) ** 0.5 < 50:
                                matched_id = obj_id
                                break

                        if matched_id is None:
                            object_id_counter += 1
                            matched_id = f"ID_{object_id_counter}"
                            object_data[matched_id] = {
                                "coords": (cx, cy),
                                "velocity": 0,
                                "total_velocity": 0,  # Ініціалізація сумарної швидкості
                                "velocity_count": 0,  # Ініціалізація кількості швидкостей
                                "start_time": current_time,
                                "last_seen": current_time,
                                "visible": False,
                            }

                        # Оновлюємо інформацію про об'єкт
                        prev_coords = object_data[matched_id]["coords"]
                        distance = ((cx - prev_coords[0]) ** 2 + (cy - prev_coords[1]) ** 2) ** 0.5
                        velocity = distance * fps
                        if velocity > 0:

                            object_data[matched_id]["coords"] = (cx, cy)
                            object_data[matched_id]["velocity"] = velocity
                            object_data[matched_id]["last_seen"] = current_time

                            # Оновлення середньої швидкості
                            object_data[matched_id]["total_velocity"] += velocity
                            object_data[matched_id]["velocity_count"] += 1

                        if not object_data[matched_id]["visible"] and \
                                current_time - object_data[matched_id]["start_time"] >= min_visible_time:
                            object_data[matched_id]["visible"] = True

                        if object_data[matched_id]["visible"]:
                            current_objects[matched_id] = object_data[matched_id]
                            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                            cv2.putText(frame, f"{matched_id}", (x, y - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                if frame_count % 5 == 0:
                    data_queue.put((object_data.copy(), frame_count, time.time() - start_time))

                for obj_id, data in list(object_data.items()):
                    if current_time - data["last_seen"] > max_disappear_time:
                        del object_data[obj_id]

                frame = cv2.resize(frame, (display_width, display_height))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = ImageTk.PhotoImage(Image.fromarray(frame))
                video_label.imgtk = img
                video_label.configure(image=img)
                prev_img = img

                time_to_wait = frame_delay - (time.time() - last_frame_time)
                if time_to_wait > 0:
                    time.sleep(time_to_wait)
                last_frame_time = time.time()

                frame_count += 1

            cap.release()
            is_playing = False
            save_data_to_json()
            video_label.configure(image=prev_img or "")

        video_thread = threading.Thread(target=play_video, daemon=True)
        video_thread.start()

    threading.Thread(target=update_table_worker, daemon=True).start()

    def stop_video():
        """Зупинка відтворення відео."""
        global is_playing, stop_event

        if not is_playing:
            print("Немає запущеного відео для зупинки.")
            return

        print("Зупинка відео...")
        stop_event.set()  # Зупиняємо потік відео
        is_playing = False  # Скидаємо статус відтворення

        time.sleep(0.1)  # Коротка пауза для завершення потоків

        # Очищуємо чергу перед наступним запуском
        while not data_queue.empty():
            try:
                data_queue.get_nowait()
            except queue.Empty:
                break

        video_label.configure(image="")  # Очистити екран
        print("Відео зупинено, черга очищена.")

    def show_about():
        messagebox.showinfo("Про програму", "Програма відстеження об'єктів у відео.\nВерсія 1.0")

    app = ttk.Window(themename="darkly")
    app.title("Відстеження об'єктів у відео")
    app.geometry("1800x1000")

    # Головний контейнер
    main_frame = ttk.Frame(app)
    main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

    # Верхній рядок з введенням відео і кнопками
    controls_frame = ttk.Frame(main_frame)
    controls_frame.pack(fill=X, pady=5)

    file_entry = ttk.Entry(controls_frame, width=150)
    file_entry.pack(side=LEFT, padx=5)

    file_button = ttk.Button(controls_frame, text="Вибрати відео", command=select_video)
    file_button.pack(side=LEFT, padx=5)

    start_button = ttk.Button(controls_frame, text="Запустити", command=start_video)
    start_button.pack(side=LEFT, padx=5)

    stop_button = ttk.Button(controls_frame, text="Зупинити", bootstyle="danger", command=stop_video)
    stop_button.pack(side=LEFT, padx=5)

    # Головний поділ: зліва таблиця, справа плеєр
    content_frame = ttk.Frame(main_frame)
    content_frame.pack(fill=BOTH, expand=True)

    # Ліва панель (таблиця)
    left_frame = ttk.Frame(content_frame, width=800)
    left_frame.pack(side=LEFT, fill=BOTH, padx=5, pady=5)

    # Таблиця для даних
    table = ttk.Treeview(left_frame,
                         columns=("Object_ID", "Frame", "X_mm", "Y_mm", "Displacement", "Velocity"),
                         show="headings")

    table.heading("Object_ID", text="Назва об'єкта")
    table.heading("Frame", text="Кадр")
    table.heading("X_mm", text="Координата X, мм")
    table.heading("Y_mm", text="Координата Y, мм")
    table.heading("Displacement", text="Переміщення, мм")
    table.heading("Velocity", text="Швидкість, мм/с")

    # Встановлення ширини колонок
    table.column("Object_ID", width=120)
    table.column("Frame", width=80)
    table.column("X_mm", width=120)
    table.column("Y_mm", width=120)
    table.column("Displacement", width=120)
    table.column("Velocity", width=120)

    # Розміщення таблиці
    table.pack(fill=BOTH, expand=True)

    # Права панель (плеєр)
    right_frame = ttk.Frame(content_frame, relief="sunken", borderwidth=2, width=1000, height=800, style="TFrame")
    right_frame.pack(side=RIGHT, padx=20, pady=20)
    right_frame.pack_propagate(False)

    # Плеєр для відео з чорним фоном
    video_label = ttk.Label(right_frame, background="black")
    video_label.pack(fill=BOTH, expand=True)

    menubar = ttk.Menu(app)
    app.config(menu=menubar)

    file_menu = ttk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="Відкрити відео", command=select_video)
    file_menu.add_command(label="Зберегти дані", command=save_data_to_json)
    file_menu.add_separator()
    file_menu.add_command(label="Вихід", command=app.quit)

    play_menu = ttk.Menu(menubar, tearoff=0)
    play_menu.add_command(label="Запустити", command=start_video)
    play_menu.add_command(label="Зупинити", command=stop_video)

    help_menu = ttk.Menu(menubar, tearoff=0)
    help_menu.add_command(label="Про програму", command=show_about)

    menubar.add_cascade(label="Файл", menu=file_menu)
    menubar.add_cascade(label="Відтворення", menu=play_menu)
    menubar.add_cascade(label="Допомога", menu=help_menu)

    settings_menu = ttk.Menu(menubar, tearoff=0)
    settings_menu.add_command(label="Налаштування", command=open_settings_window)

    menubar.add_cascade(label="Налаштування", menu=settings_menu)
    # Запуск головного циклу інтерфейсу


    app.mainloop()

# Запуск графічного інтерфейсу в окремому потоці
if __name__ == "__main__":
    gui_thread = threading.Thread(target=create_gui)
    gui_thread.start()
