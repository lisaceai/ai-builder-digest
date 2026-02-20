from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import os
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
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
