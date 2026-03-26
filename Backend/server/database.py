# models.py
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, ForeignKey, Text
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
    schedules = relationship("Schedule", back_populates="owner")

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(String, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    type = Column(String, nullable=False) # 'register' 或 'reset'
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)

# --- 原有日程表 ---
class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True) # 关联用户
    title = Column(String)
    time_range = Column(String) # 例如 "09:00-10:00"
    content = Column(Text)
    owner = relationship("User", back_populates="schedules")