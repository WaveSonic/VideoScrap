
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///database.db"  # Файл бази даних SQLite
engine = create_engine(DATABASE_URL, echo=True)  # echo=True для логів SQL-запитів

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    from models import Base  # Імпорт моделей тут, щоб уникнути циклічних імпортів
    Base.metadata.create_all(bind=engine)
