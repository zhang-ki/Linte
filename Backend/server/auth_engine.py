# auth_engine.py
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_
from passlib.context import CryptContext
from jose import jwt, JWTError
import os

from database import User, VerificationCode  # 从 database.py 导入模型
from email_service import email_service

# 配置
SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key_change_this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
CODE_EXPIRE_MINUTES = 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthEngine:
    """
    用户认证引擎
    用法:
        1. 初始化: engine = AuthEngine(db_session)
        2. 发送验证码: await engine.request_code(email, type="register")
        3. 注册: result = engine.register(email, password, code)
        4. 登录: token = engine.login(email, password)
    """

    def __init__(self, db: Session):
        self.db = db

    def _generate_code(self) -> str:
        """生成 6 位数字验证码"""
        return "".join(random.choices(string.digits, k=6))

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def _create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    async def request_code(self, email: str, code_type: str) -> bool:
        """
        请求验证码 (注册 或 找回密码)
        :param code_type: 'register' 或 'reset'
        """
        # 1. 检查频率限制 (可选：防止轰炸)
        # 这里简化逻辑：如果 1 分钟内有未过期的码，则不重发

        # 2. 生成新码
        code = self._generate_code()
        expire_time = datetime.utcnow() + timedelta(minutes=CODE_EXPIRE_MINUTES)

        # 3. 存入数据库 (覆盖旧的)
        # 先删除该邮箱该类型的旧码
        self.db.query(VerificationCode).filter(
            and_(VerificationCode.email == email, VerificationCode.type == code_type)
        ).delete()

        new_code_obj = VerificationCode(
            email=email,
            code=code,
            type=code_type,
            expires_at=expire_time,
            is_used=False
        )
        self.db.add(new_code_obj)
        self.db.commit()

        # 4. 发送邮件
        success = await email_service.send_verification_code(email, code)
        return success

    def register(self, email: str, password: str, code: str) -> Dict:
        """
        执行注册
        :return: {"user_id": "...", "token": "..."} 或 抛出异常
        """
        # 1. 验证验证码
        code_obj = self.db.query(VerificationCode).filter(
            and_(
                VerificationCode.email == email,
                VerificationCode.code == code,
                VerificationCode.type == "register",
                VerificationCode.is_used == False,
                VerificationCode.expires_at > datetime.utcnow()
            )
        ).first()

        if not code_obj:
            raise ValueError("验证码无效或已过期")

        # 2. 检查用户是否存在
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValueError("该邮箱已被注册")

        # 3. 创建用户
        user_id = f"user_{random.randint(10000, 99999)}"  # 简单生成 ID
        hashed_pw = self._hash_password(password)

        new_user = User(user_id=user_id, email=email, hashed_password=hashed_pw)
        self.db.add(new_user)

        # 标记验证码已使用
        code_obj.is_used = True

        self.db.commit()
        self.db.refresh(new_user)

        # 4. 生成 Token
        token = self._create_access_token({"sub": user_id, "email": email})

        return {"user_id": user_id, "email": email, "access_token": token, "token_type": "bearer"}

    def login(self, email: str, password: str) -> Dict:
        """
        执行登录
        """
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError("用户不存在")

        if not self._verify_password(password, user.hashed_password):
            raise ValueError("密码错误")

        token = self._create_access_token({"sub": user.user_id, "email": user.email})
        return {"user_id": user.user_id, "email": user.email, "access_token": token, "token_type": "bearer"}

    def reset_password(self, email: str, new_password: str, code: str) -> bool:
        """
        重置密码
        """
        # 1. 验证验证码
        code_obj = self.db.query(VerificationCode).filter(
            and_(
                VerificationCode.email == email,
                VerificationCode.code == code,
                VerificationCode.type == "reset",
                VerificationCode.is_used == False,
                VerificationCode.expires_at > datetime.utcnow()
            )
        ).first()

        if not code_obj:
            raise ValueError("验证码无效或已过期")

        # 2. 查找用户并更新密码
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError("用户不存在，请先注册")

        user.hashed_password = self._hash_password(new_password)
        code_obj.is_used = True  # 标记使用

        self.db.commit()
        return True