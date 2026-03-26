# email_service.py
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件中的配置


class EmailService:
    """
    QQ 邮箱发送服务
    用法:
        1. 初始化: service = EmailService()
        2. 发送: await service.send_code("user@qq.com", "123456")
    """

    def __init__(self):
        # 从环境变量读取配置，避免硬编码密码
        self.smtp_server = "smtp.qq.com"
        self.smtp_port = 465  # SSL 端口
        self.sender_email = os.getenv("QQ_EMAIL")
        self.auth_code = os.getenv("QQ_AUTH_CODE")  # 注意：这里是授权码，不是登录密码

        if not self.sender_email or not self.auth_code:
            raise ValueError("❌ 请在 .env 文件中配置 QQ_EMAIL 和 QQ_AUTH_CODE")

    async def send_verification_code(self, to_email: str, code: str):
        """
        发送验证码邮件
        :param to_email: 接收者邮箱
        :param code: 6位验证码
        """
        subject = "【日程匹配系统】验证码"
        body = f"""
        <html>
        <body>
            <h3>您好，您的验证码是：</h3>
            <h1 style="color: #007bff; font-size: 40px; letter-spacing: 5px;">{code}</h1>
            <p>该验证码 5 分钟内有效，请勿泄露给他人。</p>
            <p>如果您没有请求此操作，请忽略此邮件。</p>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = to_email

        # 添加 HTML 内容
        msg.attach(MIMEText(body, "html", "utf-8"))

        try:
            print(f"📧 正在向 {to_email} 发送验证码...")
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_server,
                port=self.smtp_port,
                username=self.sender_email,
                password=self.auth_code,
                start_tls=False,  # 465 端口不需要 start_tls
                use_tls=True
            )
            print("✅ 邮件发送成功")
            return True
        except Exception as e:
            print(f"❌ 邮件发送失败: {e}")
            return False


# 单例模式，全局复用
try:
    email_service = EmailService()
except ValueError as e:
    # 当环境变量未配置时，不在导入时抛出异常，改为使用一个降级的 Dummy 服务
    print(f"⚠️ 邮件服务未配置: {e}. 邮件功能将被禁用。")

    class _DummyEmailService:
        async def send_verification_code(self, to_email: str, code: str):
            print(f"[dummy_email_service] 发送验证码被跳过 -> {to_email}: {code}")
            return False

    email_service = _DummyEmailService()