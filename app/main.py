import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import subprocess
from pathlib import Path

# 自动加载 .env 文件中的环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="AI Builder 管理器")


@app.on_event("startup")
async def startup_event():
    """启动时从 JSON 回填 ChromaDB，确保向量搜索可用"""
    from scripts.rag_store import ensure_vector_store_ready
    try:
        ready = ensure_vector_store_ready()
        if ready:
            print("ChromaDB hydrated from JSON store on startup.")
        else:
            print("ChromaDB hydration skipped (no data or missing API key).")
    except Exception as e:
        print(f"Warning: ChromaDB startup hydration failed: {e}")


# 配置路径
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "users.json"


class UsersData(BaseModel):
    ai_builders: List[str]


class QuestionRequest(BaseModel):
    question: str
    username: Optional[str] = None
    n_results: int = 5


class TrendsRequest(BaseModel):
    days: Optional[int] = None


class BuilderAnalysisRequest(BaseModel):
    username: str


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
        subprocess.run(["git", "add", "config/users.json"], cwd=BASE_DIR, check=True)
        subprocess.run(
            ["git", "commit", "-m", "更新关注的 AI Builder 列表"],
            cwd=BASE_DIR,
            check=True,
            capture_output=True
        )
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Auto push failed: {e}")
        return False


# ==================== 原有接口 ====================

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
        pushed = auto_push()
        if pushed:
            return {"status": "success", "message": "保存成功，已推送到 GitHub"}
        else:
            return {"status": "success", "message": "保存成功（未自动推送）"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RAG 接口 ====================

@app.post("/api/rag/ask")
async def rag_ask(req: QuestionRequest):
    """RAG 问答接口"""
    try:
        from scripts.rag_qa import ask
        result = ask(
            question=req.question,
            n_results=req.n_results,
            username=req.username,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rag/trends")
async def rag_trends(days: Optional[int] = None):
    """趋势分析接口"""
    try:
        from scripts.rag_trends import analyze_trends
        result = analyze_trends(days=days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rag/builder")
async def rag_builder_analysis(req: BuilderAnalysisRequest):
    """单个 Builder 分析接口"""
    try:
        from scripts.rag_trends import analyze_builder
        result = analyze_builder(username=req.username)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rag/stats")
async def rag_stats(days: Optional[int] = None):
    """RAG 数据库统计"""
    try:
        from scripts.rag_store import get_all_tweets_stats
        return get_all_tweets_stats(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
