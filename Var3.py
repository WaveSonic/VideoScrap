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
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from db import init_db, engine
from sqlalchemy.orm import sessionmaker
init_db()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

SETTINGS_FILE = "settings.json"
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
is_playing = False
stop_event = threading.Event()
data_queue = queue.Queue()
canvas_widget = None
ax = None
x_press, y_press = None, None
is_dragging = False

def show_info_message(title, message):
    messagebox.showinfo(title, message)


def show_warning_message(title, message):
    messagebox.showwarning(title, message)


def show_error_message(title, message):
    messagebox.showerror(title, message)

def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        show_error_message("Помилка", f"Не вдалося зберегти налаштування.\n{str(e)}")


def create_gui():
    def open_statistics():
        stats_window = Toplevel(app)
        stats_window.title("Статистика")
        stats_window.geometry("400x350")
        stats_window.attributes('-topmost', True)

        ttk.Label(stats_window, text="Оберіть тип графіка:", font=("Arial", 12, "bold")).pack(pady=10)

        graph_types = {
            "Переміщення об'єктів у часі": "displacement_mm",
            "Швидкість об'єктів у часі": "average_velocity_mm_s",
            "Траєкторія руху (X vs Y)": "trajectory",
        }

        selected_graph = ttk.StringVar(value=list(graph_types.keys())[0])

        for text in graph_types.keys():
            ttk.Radiobutton(stats_window, text=text, variable=selected_graph, value=text).pack(anchor="w", padx=20)

        def select_json_and_plot():
            file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")], parent=stats_window)
            if not file_path:
                return

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                show_error_message("Помилка", "Файл містить некоректні JSON-дані.")
                return

            selected_type = graph_types[selected_graph.get()]
            plot_graph(data, selected_type)
            stats_window.destroy()

        ttk.Button(stats_window, text="Побудувати графік", command=select_json_and_plot, bootstyle="success").pack(
            pady=20)

    def plot_graph(data, graph_type):
        global canvas_widget, ax
        video_label.pack_forget()
        if canvas_widget:
            canvas_widget.get_tk_widget().destroy()

        fig, ax = plt.subplots(figsize=(7, 5))

        if graph_type in ["displacement_mm", "average_velocity_mm_s"]:
            for obj_id, entries in data.items():
                frames = [entry["frame"] for entry in entries]
                values = [entry[graph_type] for entry in entries]
                ax.plot(frames, values, marker='o', label=obj_id)

            ax.set_xlabel("Кадри")
            ax.set_ylabel("Переміщення (мм)" if graph_type == "displacement_mm" else "Швидкість (мм/с)")
            ax.set_title("Статистика об'єктів")
            ax.legend()
            ax.grid(True)

        elif graph_type == "trajectory":
            for obj_id, entries in data.items():
                x_values = [entry["x_mm"] for entry in entries]
                y_values = [entry["y_mm"] for entry in entries]
                ax.plot(x_values, y_values, marker='o', linestyle='-', label=obj_id)

            ax.set_xlabel("Координата X (мм)")
            ax.set_ylabel("Координата Y (мм)")
            ax.set_title("Траєкторія руху об'єктів")
            ax.legend()
            ax.grid(True)

        elif graph_type in ["hist_velocity", "hist_displacement"]:
            all_values = []
            for obj_id, entries in data.items():
                all_values.extend(
                    [entry["average_velocity_mm_s"] if graph_type == "hist_velocity" else entry["displacement_mm"]
                     for entry in entries])

            ax.hist(all_values, bins=10, alpha=0.7, color='b', edgecolor='black')
            ax.set_xlabel("Швидкість (мм/с)" if graph_type == "hist_velocity" else "Переміщення (мм)")
            ax.set_ylabel("Кількість об'єктів")
            ax.set_title("Гістограма швидкості" if graph_type == "hist_velocity" else "Гістограма переміщення")

        fig.canvas.mpl_connect("scroll_event", on_scroll)
        fig.canvas.mpl_connect("button_press_event", on_press)
        fig.canvas.mpl_connect("motion_notify_event", on_drag)
        fig.canvas.mpl_connect("button_release_event", on_release)

        canvas_widget = FigureCanvasTkAgg(fig, master=right_frame)
        canvas_widget.get_tk_widget().pack(fill="both", expand=True)

    def on_scroll(event):
        global ax
        if ax is None:
            return

        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()

        scale_factor = 1.1 if event.step < 0 else 0.9

        ax.set_xlim([x_min * scale_factor, x_max * scale_factor])
        ax.set_ylim([y_min * scale_factor, y_max * scale_factor])

        ax.figure.canvas.draw_idle()

    def on_press(event):
        global x_press, y_press, is_dragging
        if event.button == 1:
            x_press, y_press = event.xdata, event.ydata
            is_dragging = True

    def on_drag(event):
        global ax, x_press, y_press, is_dragging
        if not is_dragging or ax is None or x_press is None or y_press is None:
            return

        if event.xdata is None or event.ydata is None:
            return

        dx = x_press - event.xdata
        dy = y_press - event.ydata

        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()

        ax.set_xlim([x_min + dx, x_max + dx])
        ax.set_ylim([y_min + dy, y_max + dy])

        ax.figure.canvas.draw_idle()

    def on_release(event):
        global is_dragging
        is_dragging = False

    def clear_graph():
        global canvas_widget

        if canvas_widget:
            canvas_widget.get_tk_widget().destroy()
            canvas_widget = None

        video_label.pack(fill="both", expand=True)

    def open_settings_window():
        """Відкриває вікно налаштувань."""
        settings_window = Toplevel(app)
        settings_window.title("Налаштування")
        settings_window.geometry("500x300")
        settings_window.attributes('-topmost', True)

        def update_setting(key, value):
            settings[key] = value
            save_settings()

        def update_slider(event, key, slider):
            try:
                value = event.widget.get().replace(",", ".")
                value = float(value)
                value = max(slider.cget("from"), min(value, slider.cget("to")))
                slider.set(value)
                update_setting(key, value)
            except ValueError:
                pass

        def update_entry(slider, entry, key):
            value = round(slider.get(), 2)
            entry.delete(0, END)
            entry.insert(0, f"{value:.2f}".replace(".", ","))
            update_setting(key, value)

        def create_setting_row(label_text, key, from_, to_, step, description):
            frame = ttk.Frame(settings_window)
            frame.pack(fill=X, padx=10, pady=5)

            ttk.Label(frame, text=label_text, width=18, anchor=W).pack(side=LEFT)
            slider = Scale(frame, from_=from_, to=to_, orient=HORIZONTAL, resolution=step,
                           command=lambda v: update_entry(slider, entry, key))
            slider.set(settings[key])
            slider.pack(side=LEFT, fill=X, expand=True, padx=5)

            entry = ttk.Entry(frame, width=6)
            entry.insert(0, f"{settings[key]:.2f}".replace(".", ","))
            entry.pack(side=LEFT, padx=5)
            entry.bind("<Return>", lambda event, k=key, s=slider: update_slider(event, k, s))

            ttk.Label(frame, text=description, width=18, anchor=W).pack(side=LEFT)  # Опис

        ttk.Label(settings_window, text="Налаштування виявлення об'єктів", font=("Arial", 12, "bold")).pack(pady=5)
        create_setting_row("Довжина історії:", "history", 100, 2000, 100, "Чутливість до старих об'єктів")
        create_setting_row("Поріг руху:", "varThreshold", 10, 100, 1, "Від 10 - дуже чутливий")
        create_setting_row("Мін. площа (px²):", "min_contour_area", 500, 5000, 100, "Фільтр дрібних об'єктів")

        def reset_settings():
            global settings
            settings = default_settings.copy()
            save_settings()
            settings_window.destroy()
            open_settings_window()
            messagebox.showinfo("Налаштування", "Налаштування скинуто до стандартних значень.")

        def save_and_close():
            save_settings()
            messagebox.showinfo("Збереження", "Налаштування збережено успішно.")
            settings_window.destroy()

        btn_frame = ttk.Frame(settings_window)
        btn_frame.pack(fill=X, pady=10)

        ttk.Button(btn_frame, text="Скинути налаштування", command=reset_settings, bootstyle="danger").pack(side=LEFT,
                                                                                                            padx=10)
        ttk.Button(btn_frame, text="Зберегти", command=save_and_close, bootstyle="success").pack(side=RIGHT, padx=10)

    def save_data_to_json():
        if not tracked_data:
            show_warning_message("Увага", "Немає даних для збереження!")
            return

        filepath = file_entry.get()
        if not filepath:
            show_warning_message("Помилка", "Будь ласка, виберіть відеофайл.")
            return

        video_name = filepath.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{video_name}_{timestamp}.json"

        try:
            with open(filename, "w", encoding="utf-8") as json_file:
                json.dump(tracked_data, json_file, indent=4, ensure_ascii=False)
            show_info_message("Збережено", f"Дані успішно збережені у файл: {filename}")
        except Exception as e:
            show_error_message("Помилка", f"Не вдалося зберегти дані.\n{str(e)}")


    def update_table_worker():

        while True:  # Без перевірки stop_event
            try:
                objects, frame_count, elapsed_time = data_queue.get(timeout=1)
                table.after(0, update_table, objects, frame_count)
            except queue.Empty:
                continue

    def update_table(objects, frame_count):
        pixel_to_mm = 0.1

        existing_ids = {table.item(row)["values"][0] for row in table.get_children()}

        for obj_id, data in objects.items():
            x_pixel, y_pixel = data["coords"]
            x_mm, y_mm = x_pixel * pixel_to_mm, y_pixel * pixel_to_mm

            prev_x, prev_y = data.get("prev_coords", (x_pixel, y_pixel))
            displacement = ((x_pixel - prev_x) ** 2 + (y_pixel - prev_y) ** 2) ** 0.5 * pixel_to_mm
            data["prev_coords"] = (x_pixel, y_pixel)

            average_velocity = data["total_velocity"] / data["velocity_count"] if data["velocity_count"] > 0 else 0
            size_mm = data.get("size_mm", 0)
            if average_velocity == 0:
                continue

            if obj_id in existing_ids:
                for row in table.get_children():
                    if table.item(row)["values"][0] == obj_id:
                        table.item(row, values=(
                            obj_id, frame_count,
                            round(x_mm, 3), round(y_mm, 3),
                            round(displacement, 3), round(average_velocity, 3),
                            round(size_mm, 3)
                        ))
                        break
            else:
                table.insert("", "end", values=(
                    obj_id, frame_count,
                    round(x_mm, 3), round(y_mm, 3),
                    round(displacement, 3), round(average_velocity, 3),
                    round(size_mm, 3)
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
        filepath = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi;*.mkv")])
        if filepath:
            file_entry.delete(0, END)
            file_entry.insert(0, filepath)

    def start_video():
        global is_playing, stop_event, tracked_data
        if is_playing:
            show_warning_message("Увага", "Відео вже запущено!")
            return
        clear_graph()
        filepath = file_entry.get()
        if not filepath:
            show_warning_message("Помилка", "Будь ласка, виберіть відеофайл.")
            return

        for row in table.get_children():
            table.delete(row)


        tracked_data = {}


        def play_video():
            global is_playing
            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                show_error_message("Помилка", f"Не вдалося відкрити відео: {filepath}")
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
                    show_info_message("Відео завершено", "Відтворення відео завершено.")
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
                        pixel_to_mm = 0.1
                        size_mm = (w * h) * pixel_to_mm
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
                                "size_mm": size_mm,
                                "velocity": 0,
                                "total_velocity": 0,
                                "velocity_count": 0,
                                "start_time": current_time,
                                "last_seen": current_time,
                                "visible": False,
                            }


                        prev_coords = object_data[matched_id]["coords"]
                        distance = ((cx - prev_coords[0]) ** 2 + (cy - prev_coords[1]) ** 2) ** 0.5
                        velocity = distance * fps
                        if velocity > 0:

                            object_data[matched_id]["coords"] = (cx, cy)
                            object_data[matched_id]["velocity"] = velocity
                            object_data[matched_id]["last_seen"] = current_time

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
        global is_playing, stop_event

        if not is_playing:
            show_warning_message("Увага", "Немає запущеного відео для зупинки.")
            return

        print("Зупинка відео...")
        stop_event.set()  # Зупиняємо потік відео
        is_playing = False  # Скидаємо статус відтворення
        show_info_message("Зупинка", "Відтворення відео зупинено.")
        time.sleep(0.1)  # Коротка пауза для завершення потоків

        while not data_queue.empty():
            try:
                data_queue.get_nowait()
            except queue.Empty:
                break

        video_label.configure(image="")
        print("Відео зупинено, черга очищена.")

    def show_about():
        messagebox.showinfo("Про програму", "Програма відстеження об'єктів у відео.\nВерсія 1.0")

    def on_close():
        global is_playing, stop_event

        if messagebox.askyesno("Вихід", "Ви дійсно хочете вийти з програми?"):
            stop_event.set()
            is_playing = False

            while not data_queue.empty():
                try:
                    data_queue.get_nowait()
                except queue.Empty:
                    break

            app.destroy()
            os._exit(0)

    app = ttk.Window(themename="darkly")
    app.title("Відстеження об'єктів у відео")
    app.geometry("1800x1000")
    app.protocol("WM_DELETE_WINDOW", on_close)

    main_frame = ttk.Frame(app)
    main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

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


    content_frame = ttk.Frame(main_frame)
    content_frame.pack(fill=BOTH, expand=True)


    left_frame = ttk.Frame(content_frame, width=800)
    left_frame.pack(side=LEFT, fill=BOTH, padx=5, pady=5)


    table = ttk.Treeview(left_frame,
                         columns=("Object_ID", "Frame", "X_mm", "Y_mm", "Displacement", "Velocity", "Size_mm"),
                         show="headings")

    table.heading("Object_ID", text="Назва об'єкта")
    table.heading("Frame", text="Кадр")
    table.heading("X_mm", text="Координата X, мм")
    table.heading("Y_mm", text="Координата Y, мм")
    table.heading("Displacement", text="Переміщення, мм")
    table.heading("Velocity", text="Швидкість, мм/с")
    table.heading("Size_mm", text="Розмір об'єкта, мм")

    table.column("Object_ID", width=120)
    table.column("Frame", width=80)
    table.column("X_mm", width=120)
    table.column("Y_mm", width=120)
    table.column("Displacement", width=120)
    table.column("Velocity", width=120)
    table.column("Size_mm", width=120)

    table.pack(fill=BOTH, expand=True)

    right_frame = ttk.Frame(content_frame, relief="sunken", borderwidth=2, width=1000, height=800, style="TFrame")
    right_frame.pack(side=RIGHT, padx=20, pady=20)
    right_frame.pack_propagate(False)

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
    statistics_menu = ttk.Menu(menubar, tearoff=0)
    statistics_menu.add_command(label="Показати статистику", command=open_statistics)
    menubar.add_cascade(label="Статистика", menu=statistics_menu)
    menubar.add_cascade(label="Налаштування", menu=settings_menu)
    app.mainloop()

if __name__ == "__main__":
    gui_thread = threading.Thread(target=create_gui)
    gui_thread.start()
