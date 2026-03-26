
import os
from datetime import datetime
from typing import List, Optional
import socket
import subprocess
import re
import time


# 1. 先加载环境变量 (最重要！必须在导入其他自定义模块前做)
from dotenv import load_dotenv

load_dotenv()

# 2. 导入 FastAPI 相关
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import uvicorn

# 3. 导入数据库 (此时环境变量已加载，数据库配置应该正常)
try:
    from database import engine, Base, get_db, User, Schedule

    # 初始化数据库表
    Base.metadata.create_all(bind=engine)
    print("数据库初始化成功")
except Exception as e:
    print(f"[ERROR] 数据库初始化失败: {e}")
    raise e

# 4. 导入认证引擎
try:
    from auth_engine import AuthEngine

    print("认证引擎导入成功")
except Exception as e:
    print(f"[ERROR] 认证引擎导入失败: {e}")
    raise e

# 5. 尝试导入匹配引擎 (允许失败，不影响核心功能)
match_engine = None
try:
    from match import MatcherEngine

    # 模型下载到当前项目目录下的 `model/bge-large-zh-v1.5`
    # 用相对路径避免写死盘符（比如 D:\）
    model_path =r"D:\models\bge-large-zh-v1.5"

    if os.path.exists(model_path):
        print("正在加载大模型...（可能需要几十秒）")
        match_engine = MatcherEngine(model_path=model_path)
        print("匹配引擎加载成功")
    else:
        print(f"[WARN] 未找到模型文件夹 '{model_path}'")
        print("匹配功能将不可用，但注册/登录/日程功能正常。")
except Exception as e:
    print(f"[WARN] 匹配引擎加载异常: {e}")
    print("服务器将继续运行，仅匹配接口不可用。")

# ================= 创建 App =================
app = FastAPI(title="日程匹配与认证系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================= 数据模型 (Schemas) =================
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    code: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ResetPassword(BaseModel):
    email: EmailStr
    new_password: str
    code: str


class SendCodeReq(BaseModel):
    email: EmailStr
    type: str


class ScheduleItem(BaseModel):
    id: Optional[str] = None
    title: str
    time_range: str
    content: str


class MatchRequest(BaseModel):
    my_profile: ScheduleItem
    candidates: List[ScheduleItem]


# ================= 接口定义 =================

@app.post("/api/auth/send-code")
async def send_code(req: SendCodeReq, db: Session = Depends(get_db)):
    auth = AuthEngine(db)
    if req.type not in ["register", "reset"]:
        raise HTTPException(400, "类型错误")
    success = await auth.request_code(req.email, req.type)
    if not success:
        # 如果是 Dummy 服务，这里会返回 False，但在测试环境我们可以假装成功
        if os.getenv("QQ_EMAIL"):
            raise HTTPException(500, "邮件发送失败")
        else:
            return {"msg": "验证码已生成 (模拟模式，请查看控制台日志)"}
    return {"msg": "验证码已发送"}


@app.post("/api/auth/register")
def register(req: UserRegister, db: Session = Depends(get_db)):
    auth = AuthEngine(db)
    try:
        return auth.register(req.email, req.password, req.code)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/login")
def login(req: UserLogin, db: Session = Depends(get_db)):
    auth = AuthEngine(db)
    try:
        return auth.login(req.email, req.password)
    except ValueError as e:
        raise HTTPException(401, str(e))


@app.post("/api/auth/reset-password")
def reset_password(req: ResetPassword, db: Session = Depends(get_db)):
    auth = AuthEngine(db)
    try:
        auth.reset_password(req.email, req.new_password, req.code)
        return {"msg": "密码重置成功"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/schedule/")
def create_schedule(item: ScheduleItem, db: Session = Depends(get_db)):
    temp_user_id = "temp_user_001"
    db_item = Schedule(
        id=item.id or f"sched_{datetime.now().timestamp()}",
        user_id=temp_user_id,
        title=item.title,
        time_range=item.time_range,
        content=item.content
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@app.get("/api/schedule/")
def get_schedules(db: Session = Depends(get_db)):
    return db.query(Schedule).all()


@app.delete("/api/schedule/{schedule_id}")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)):
    item = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not item:
        raise HTTPException(404, "日程未找到")
    db.delete(item)
    db.commit()
    return {"msg": "删除成功"}


@app.post("/api/match")
def run_match(req: MatchRequest):
    if not match_engine:
        raise HTTPException(503, "匹配引擎未加载 (缺少模型文件或库)")

    p = (req.my_profile.id or "p1", req.my_profile.time_range, req.my_profile.content)
    c_list = [(c.id or f"c{i}", c.time_range, c.content) for i, c in enumerate(req.candidates)]

    result = match_engine.match(p, c_list)
    return {"matches": [{"id": r[0], "time": r[1], "content": r[2]} for r in result]}


if __name__ == "__main__":
    def _port_available(p: int) -> bool:
        # 通过“尝试绑定”判断端口是否可用（立即释放 socket）
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # 不使用 SO_REUSEADDR，避免“误判端口已被占用但仍能 bind”的情况
                s.bind(("0.0.0.0", p))
                return True
            except OSError:
                return False

    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def _kill_process_on_port(p: int) -> None:
        # 仅用于开发环境：尝试查找并终止监听该端口的进程
        try:
            output = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except Exception:
            return

        for line in output.splitlines():
            if f":{p}" not in line:
                continue
            if "LISTENING" not in line.upper():
                continue
            m = re.search(r"\s(\d+)\s*$", line)
            if not m:
                continue
            pid = m.group(1)
            try:
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                time.sleep(0.6)
            except Exception:
                pass

    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8000"))

    print("服务器正在启动...")

    # 尝试自动释放端口（避免反复报 winerror 10048）
    for _ in range(3):
        if _port_available(port):
            break
        print(f"[WARN] 端口 {port} 已被占用，尝试自动结束占用进程...")
        _kill_process_on_port(port)
        time.sleep(1)
    else:
        port = _find_free_port()
        print(f"[WARN] 自动释放失败，改用端口 {port}")

    print(f"本地访问: http://127.0.0.1:{port}")
    print(f"文档地址: http://127.0.0.1:{port}/docs")
    uvicorn.run(app, host=host, port=port)
