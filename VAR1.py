import cv2
import numpy as np
import threading
import queue
import time
import math


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
            stop_event.set()
            break

        try:
            frame_queue.put(frame, timeout=1)
        except queue.Full:
            print("Черга кадрів заповнена. Пропуск кадру.")

    cap.release()


def video_processor(frame_queue, stop_event):
    """Потік для обробки відео."""
    back_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=20, detectShadows=False)
    object_data = {}  # Зберігання даних для кожного ID
    frame_count = 0
    id_counter = 0  # Лічильник для унікальних ID

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
                        "updated": True  # Маркер для оновлених об'єктів
                    }

                current_ids.add(matched_id)
                prev_coords = object_data[matched_id]["coords"]
                prev_time = object_data[matched_id]["time"]

                # Обчислення відстані та швидкості
                distance = calculate_distance(prev_coords[0], prev_coords[1], cx, cy)
                elapsed_time = time.time() - prev_time
                velocity = distance / elapsed_time if elapsed_time > 0 else 0

                # Оновлення координат і даних об'єкта
                updated = distance > 1  # Якщо координати змінилися більше ніж на 1 піксель
                object_data[matched_id].update({
                    "coords": (cx, cy),
                    "time": time.time(),
                    "distance": distance,
                    "velocity": velocity,
                    "updated": updated
                })

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, matched_id, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # Видалення об'єктів, які відсутні в кадрі
        for obj_id in list(object_data.keys()):
            if obj_id not in current_ids:
                current_time = time.time()
                elapsed_time = current_time - object_data[obj_id]["time"]
                if elapsed_time > 5:  # Видалення об'єктів, які не виявлені більше 5 секунд
                    print(f"Об'єкт {obj_id} видалено через відсутність у кадрі.")
                    del object_data[obj_id]

        print(f"Кадр {frame_count + 1}:")
        for obj_id, data in object_data.items():
            if data["updated"]:  # Виводимо тільки об'єкти, які змінили координати
                print(f"  {obj_id}: Координати: {data['coords']}, Відстань: {data['distance']:.2f}, Швидкість: {data['velocity']:.2f}")

        cv2.imshow("Рухомі об'єкти", frame)

        frame_count += 1
        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_event.set()
            break

    cv2.destroyAllWindows()




def track_moving_objects(source):
    """Головна функція."""
    frame_queue = queue.Queue(maxsize=20)
    stop_event = threading.Event()

    reader_thread = threading.Thread(target=video_reader, args=(source, frame_queue, stop_event))
    processor_thread = threading.Thread(target=video_processor, args=(frame_queue, stop_event))

    reader_thread.start()
    processor_thread.start()

    reader_thread.join()
    processor_thread.join()


# Виклик функції
track_moving_objects("176796-856056418_tiny.mp4")
