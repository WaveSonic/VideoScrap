from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base

### **Таблиця користувачів**
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")  # "user" або "admin"
    created_at = Column(DateTime, default=datetime.utcnow)

    videos = relationship("Video", back_populates="owner")

### **Таблиця відео**
class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_size = Column(Float, nullable=False)  # Розмір у мегабайтах
    upload_date = Column(DateTime, default=datetime.utcnow)
    resolution = Column(String, nullable=True)  # Наприклад, "1920x1080"
    duration = Column(Float, nullable=True)  # Тривалість у секундах
    user_id = Column(Integer, ForeignKey("users.id"))  # Прив'язка до власника

    owner = relationship("User", back_populates="videos")
    processed_video = relationship("ProcessedVideo", back_populates="video")

### **Таблиця обробленого відео**
class ProcessedVideo(Base):
    __tablename__ = "processed_videos"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    object_id = Column(String, nullable=False)  # Унікальний ідентифікатор об'єкта
    frame_number = Column(Integer, nullable=False)
    x_position = Column(Float, nullable=False)  # X координата об'єкта
    y_position = Column(Float, nullable=False)  # Y координата об'єкта
    displacement = Column(Float, nullable=False)  # Переміщення об'єкта
    velocity = Column(Float, nullable=False)  # Швидкість руху

    video = relationship("Video", back_populates="processed_video")
