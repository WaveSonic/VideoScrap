import cv2
import numpy as np
from sklearn.cluster import DBSCAN

def optical_flow_tracking_grouped_objects(source=0):
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"Не вдалося відкрити джерело: {source}")
        return

    print(f"Відео '{source}' успішно відкрито. Натисніть 'q' для виходу.")

    # Читаємо перший кадр і конвертуємо його у відтінки сірого
    ret, prev_frame = cap.read()
    if not ret:
        print("Не вдалося зчитати перший кадр.")
        return
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    # Ініціалізація початкових точок для відстеження
    feature_params = dict(maxCorners=500, qualityLevel=0.05, minDistance=3, blockSize=7)
    prev_points = cv2.goodFeaturesToTrack(prev_gray, mask=None, **feature_params)

    # Параметри для Lucas-Kanade Optical Flow
    lk_params = dict(winSize=(15, 15), maxLevel=2,
                     criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))

    # Лічильник кадрів для періодичного оновлення точок
    frame_counter = 0
    refresh_interval = 10  # Оновлювати точки через кожні 10 кадрів

    # Мінімальне зміщення для фільтрації точок
    min_motion_threshold = 2  # У пікселях

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Кінець відео або помилка читання кадру.")
            break

        # Конвертація поточного кадру у відтінки сірого
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Якщо потрібно оновити точки
        if frame_counter % refresh_interval == 0 or prev_points is None or len(prev_points) == 0:
            prev_points = cv2.goodFeaturesToTrack(gray_frame, mask=None, **feature_params)

        if prev_points is not None:
            # Розрахунок оптичного потоку
            next_points, status, error = cv2.calcOpticalFlowPyrLK(prev_gray, gray_frame, prev_points, None, **lk_params)

            if next_points is not None and status is not None:
                # Фільтруємо лише ті точки, які успішно відстежуються
                good_new = next_points[status == 1]
                good_old = prev_points[status == 1]

                # Фільтрація точок за зміщенням
                significant_motion_points = []
                for new, old in zip(good_new, good_old):
                    x_new, y_new = new.ravel()
                    x_old, y_old = old.ravel()
                    motion = np.sqrt((x_new - x_old)**2 + (y_new - y_old)**2)

                    if motion > min_motion_threshold:  # Залишаємо тільки значні рухи
                        significant_motion_points.append((x_new, y_new))

                # Групування близьких точок у об'єкти
                if significant_motion_points:
                    clustering = DBSCAN(eps=20, min_samples=2).fit(significant_motion_points)
                    labels = clustering.labels_

                    # Групуємо точки за кластерами
                    for cluster_id in set(labels):
                        if cluster_id == -1:
                            continue  # Пропускаємо шум

                        cluster_points = np.array([significant_motion_points[i] for i in range(len(labels)) if labels[i] == cluster_id])
                        x_min, y_min = cluster_points.min(axis=0)
                        x_max, y_max = cluster_points.max(axis=0)

                        # Малюємо зелену рамку навколо групи точок
                        cv2.rectangle(frame, (int(x_min), int(y_min)), (int(x_max), int(y_max)), (0, 255, 0), 2)

                # Оновлюємо попередні точки
                if len(significant_motion_points) > 0:
                    prev_points = np.array(significant_motion_points, dtype=np.float32).reshape(-1, 1, 2)
                else:
                    prev_points = None

        # Відображаємо результат
        cv2.imshow("Grouped Motion Tracking", frame)

        # Оновлюємо попередній кадр
        prev_gray = gray_frame.copy()
        frame_counter += 1

        # Вихід із циклу при натисканні клавіші 'q'
        if cv2.waitKey(20) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

# Виклик функції
optical_flow_tracking_grouped_objects("176796-856056418_tiny.mp4")
