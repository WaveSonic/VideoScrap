import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, Toplevel
from sqlalchemy.orm import sessionmaker
from db import engine
from models import User
from Var3 import create_gui  # Імпортуємо основне вікно програми

SessionLocal = sessionmaker(bind=engine)
def register_window():
    """Вікно реєстрації нового користувача"""
    reg_app = ttk.Window(themename="darkly")
    reg_app.title("Реєстрація")
    reg_app.geometry("400x350")
    reg_app.resizable(False, False)

    ttk.Label(reg_app, text="Реєстрація нового користувача", font=("Arial", 14, "bold")).pack(pady=10)

    ttk.Label(reg_app, text="Ім'я:").pack(anchor="w", padx=20)
    first_name_entry = ttk.Entry(reg_app, width=40)
    first_name_entry.pack(padx=20, pady=2)

    ttk.Label(reg_app, text="Прізвище:").pack(anchor="w", padx=20)
    last_name_entry = ttk.Entry(reg_app, width=40)
    last_name_entry.pack(padx=20, pady=2)

    ttk.Label(reg_app, text="Email:").pack(anchor="w", padx=20)
    email_entry = ttk.Entry(reg_app, width=40)
    email_entry.pack(padx=20, pady=2)

    ttk.Label(reg_app, text="Пароль:").pack(anchor="w", padx=20)
    password_entry = ttk.Entry(reg_app, width=40, show="*")
    password_entry.pack(padx=20, pady=2)

    def register():
        """Функція реєстрації нового користувача"""
        first_name = first_name_entry.get().strip()
        last_name = last_name_entry.get().strip()
        email = email_entry.get().strip()
        password = password_entry.get().strip()

        if not first_name or not last_name or not email or not password:
            messagebox.showwarning("Помилка", "Заповніть всі поля!")
            return

        session = SessionLocal()
        existing_user = session.query(User).filter(User.email == email).first()

        if existing_user:
            messagebox.showerror("Помилка", "Користувач з таким email вже існує!")
            session.close()
            return

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=password  # ⚠️ Додати хешування перед збереженням
        )

        session.add(new_user)
        session.commit()
        session.close()

        messagebox.showinfo("Успіх", "Реєстрація завершена! Тепер увійдіть у систему.")
        reg_app.destroy()
        login_window()  # Повернення до вікна входу

    ttk.Button(reg_app, text="Зареєструватися", command=register, bootstyle="success").pack(pady=10)
    ttk.Button(reg_app, text="Назад до входу", command=lambda: [reg_app.destroy(), login_window()], bootstyle="info").pack()

    reg_app.mainloop()

def login_window():
    """Головне вікно входу в систему"""
    login_app = ttk.Window(themename="darkly")
    login_app.title("Авторизація")
    login_app.geometry("400x300")
    login_app.resizable(False, False)

    ttk.Label(login_app, text="Вхід у систему", font=("Arial", 14, "bold")).pack(pady=15)

    ttk.Label(login_app, text="Email:").pack(anchor="w", padx=20)
    email_entry = ttk.Entry(login_app, width=40)
    email_entry.pack(padx=20, pady=5)

    ttk.Label(login_app, text="Пароль:").pack(anchor="w", padx=20)
    password_entry = ttk.Entry(login_app, width=40, show="*")
    password_entry.pack(padx=20, pady=5)

    def login():
        """Функція перевірки користувача та входу в систему"""
        email = email_entry.get().strip()
        password = password_entry.get().strip()

        if not email or not password:
            messagebox.showwarning("Помилка", "Заповніть всі поля!")
            return

        session = SessionLocal()
        user = session.query(User).filter(User.email == email).first()
        session.close()

        if user and user.password_hash == password:  # ⚠️ Тут має бути хешування пароля
            messagebox.showinfo("Успіх", f"Ласкаво просимо, {user.first_name}!")
            login_app.destroy()
            create_gui()  # Запуск головного інтерфейсу
        else:
            messagebox.showerror("Помилка", "Невірний email або пароль!")

    def open_register():
        """Відкриває вікно реєстрації"""
        login_app.destroy()
        register_window()

    ttk.Button(login_app, text="Увійти", command=login, bootstyle="success").pack(pady=10)
    ttk.Button(login_app, text="Реєстрація", command=open_register, bootstyle="info").pack()
    ttk.Button(login_app, text="Вийти", command=login_app.quit, bootstyle="danger").pack(pady=5)

    login_app.mainloop()

login_window()
