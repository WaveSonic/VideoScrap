from cx_Freeze import setup, Executable
import sys

# Перевіряємо, чи це Windows (необхідно для GUI-додатків)
base = None
if sys.platform == "win32":
    base = "Win32GUI"  # Використовується, якщо це GUI-програма (без консолі)

# Основний файл програми (переконайтеся, що `main_script.py` існує)
executables = [Executable("Var3.py", base=base)]

# Налаштування збірки
setup(
    name="VideoScrap",
    version="0.5",
    description="Програма для аналізу відео та побудови графіків",
    options={
        "build_exe": {
            "includes": ["numpy", "cv2", "matplotlib", "tkinter"],
            "excludes": ["unittest"],
            "optimize": 2,
            "include_files": [],
        }
    },
    executables=executables
)
