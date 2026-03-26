# models.py
from sqlalchemy import create_engine, Integer, Column, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./schedule.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- 用户与认证表 ---
class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 【新增】地理位置相关字段
    latitude = Column(Float, nullable=True)  # 纬度 (-90 到 90)
    longitude = Column(Float, nullable=True)  # 经度 (-180 到 180)
    last_location_update = Column(DateTime, nullable=True)  # 最后位置更新时间

    schedules = relationship("Schedule", back_populates="owner")


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False)
    type = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)


# --- 原有日程表 ---
class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True)
    title = Column(String)
    time_range = Column(String)
    content = Column(Text)
    owner = relationship("User", back_populates="schedules")