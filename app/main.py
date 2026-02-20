from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import os
import subprocess
from pathlib import Path

app = FastAPI(title="AI Builder 管理器")

# 配置路径
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "users.json"


class UsersData(BaseModel):
    ai_builders: list[str]


def read_users() -> UsersData:
    """读取 users.json"""
    if not CONFIG_FILE.exists():
        return UsersData(ai_builders=[])
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return UsersData(**data)


def write_users(data: UsersData) -> None:
    """写入 users.json"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data.model_dump(), f, ensure_ascii=False, indent=2)


def auto_push() -> bool:
    """自动提交并推送到 GitHub"""
    try:
        # 添加文件
        subprocess.run(["git", "add", "config/users.json"], cwd=BASE_DIR, check=True)
        # 提交
        subprocess.run(
            ["git", "commit", "-m", "更新关注的 AI Builder 列表"],
            cwd=BASE_DIR,
            check=True,
            capture_output=True
        )
        # 推送
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Auto push failed: {e}")
        return False


@app.get("/")
async def index():
    """返回前端页面"""
    return FileResponse("app/static/index.html")


@app.get("/api/users", response_model=UsersData)
async def get_users():
    """获取用户列表"""
    return read_users()


@app.post("/api/users")
async def save_users(data: UsersData):
    """保存用户列表"""
    try:
        write_users(data)
        # 尝试自动推送
        pushed = auto_push()
        if pushed:
            return {"status": "success", "message": "保存成功，已推送到 GitHub"}
        else:
            return {"status": "success", "message": "保存成功（未自动推送）"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
