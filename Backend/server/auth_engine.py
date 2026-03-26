# auth_engine.py
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_
# ❌ 移除 passlib
# from passlib.context import CryptContext
import bcrypt  # ✅ 直接使用 bcrypt
from jose import jwt, JWTError
import os

from database import User, VerificationCode
from email_service import email_service

# 配置
SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key_change_this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
CODE_EXPIRE_MINUTES = 5


# ❌ 移除 pwd_context
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthEngine:
    def __init__(self, db: Session):
        self.db = db

    def _generate_code(self) -> str:
        return "".join(random.choices(string.digits, k=6))

    def _hash_password(self, password: str) -> str:
        """
        直接使用 bcrypt 哈希密码，包含严格的长度截断保护
        """
        # 1. 转为 bytes
        password_bytes = password.encode('utf-8')

        # 2. 【核心修复】强制截断至 72 字节 (bcrypt 硬性限制)
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
            print(f"[WARN] 密码过长，已截断至 72 字节")

        # 3. 生成 salt 并哈希 (bcrypt.hashpw 返回 bytes)
        # gensalt() 默认生成 12 轮，足够安全
        hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())

        # 4. 转回 string 以便存入数据库
        return hashed_bytes.decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        直接使用 bcrypt 验证密码
        """
        try:
            # 1. 转为 bytes
            plain_bytes = plain_password.encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')

            # 2. 同样需要截断 plain_password，确保与哈希时逻辑一致
            if len(plain_bytes) > 72:
                plain_bytes = plain_bytes[:72]

            # 3. 验证
            # bcrypt.checkpw 返回 True/False
            return bcrypt.checkpw(plain_bytes, hashed_bytes)
        except Exception as e:
            print(f"[ERROR] 密码验证过程出错: {e}")
            return False

    def _create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    async def request_code(self, email: str, code_type: str) -> bool:
        code = self._generate_code()
        expire_time = datetime.utcnow() + timedelta(minutes=CODE_EXPIRE_MINUTES)

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

        success = await email_service.send_verification_code(email, code)
        return success

    def register(self, email: str, password: str, code: str) -> Dict:
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
        user_id = f"user_{random.randint(10000, 99999)}"

        # 调用新的哈希方法
        try:
            hashed_pw = self._hash_password(password)
        except Exception as e:
            raise ValueError(f"密码处理失败: {str(e)}")

        new_user = User(user_id=user_id, email=email, hashed_password=hashed_pw)
        self.db.add(new_user)

        code_obj.is_used = True
        self.db.commit()
        self.db.refresh(new_user)

        token = self._create_access_token({"sub": user_id, "email": email})
        return {"user_id": user_id, "email": email, "access_token": token, "token_type": "bearer"}

    def login(self, email: str, password: str) -> Dict:
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError("用户不存在")

        if not self._verify_password(password, user.hashed_password):
            raise ValueError("密码错误")

        token = self._create_access_token({"sub": user.user_id, "email": user.email})
        return {"user_id": user.user_id, "email": user.email, "access_token": token, "token_type": "bearer"}

    def reset_password(self, email: str, new_password: str, code: str) -> bool:
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

        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError("用户不存在，请先注册")

        user.hashed_password = self._hash_password(new_password)
        code_obj.is_used = True
        self.db.commit()
        return True