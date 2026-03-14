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
    """启动时将 Pinecone 数据同步到本地缓存，供趋势分析和关键词搜索使用"""
    from scripts.rag_store import ensure_vector_store_ready
    try:
        ready = ensure_vector_store_ready()
        if not ready:
            print("Pinecone sync skipped (no data or missing API key).")
    except Exception as e:
        print(f"Warning: Pinecone startup sync failed: {e}")


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
    import asyncio
    from functools import partial
    try:
        from scripts.rag_qa import ask
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(ask, question=req.question, n_results=req.n_results, username=req.username),
            ),
            timeout=28.0,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="请求超时，请稍后重试（Zhipu API 响应较慢）")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rag/trends")
async def rag_trends(days: Optional[int] = None):
    """趋势分析接口"""
    import asyncio
    from functools import partial
    try:
        from scripts.rag_trends import analyze_trends
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, partial(analyze_trends, days=days)),
            timeout=28.0,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="请求超时，请稍后重试（Zhipu API 响应较慢）")
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


@app.post("/api/rag/sync")
async def rag_sync():
    """手动从 Pinecone 同步最新推文到本地缓存"""
    try:
        from scripts.rag_store import HAS_PINECONE, _sync_from_pinecone, _load_json_store
        if not HAS_PINECONE or not os.environ.get("PINECONE_API_KEY", ""):
            raise HTTPException(status_code=503, detail="Pinecone 未配置，无法同步。请检查 PINECONE_API_KEY 环境变量。")
        count = _sync_from_pinecone()
        local_total = len(_load_json_store())
        return {"synced": count, "local_total": local_total, "message": f"同步完成，本地共 {local_total} 条推文"}
    except HTTPException:
        raise
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


@app.get("/api/health")
async def health_check():
    """健康检查 - 报告各组件配置状态"""
    zhipu_key_set = bool(os.environ.get("ZHIPU_API_KEY", ""))
    pinecone_key_set = bool(os.environ.get("PINECONE_API_KEY", ""))

    pinecone_ok = False
    pinecone_count = 0
    try:
        from scripts.rag_store import HAS_PINECONE, get_pinecone_index
        if HAS_PINECONE and pinecone_key_set:
            index = get_pinecone_index()
            stats = index.describe_index_stats()
            pinecone_count = stats.total_vector_count
            pinecone_ok = True
    except Exception:
        pass

    json_count = 0
    try:
        from scripts.rag_store import _load_json_store
        json_count = len(_load_json_store())
    except Exception:
        pass

    all_ok = zhipu_key_set and pinecone_ok

    return {
        "status": "ok" if all_ok else "degraded",
        "components": {
            "zhipu_api_key": "configured" if zhipu_key_set else "MISSING - 请设置 ZHIPU_API_KEY",
            "pinecone_api_key": "configured" if pinecone_key_set else "MISSING - 请设置 PINECONE_API_KEY",
            "pinecone": f"ok ({pinecone_count} tweets)" if pinecone_ok else "unavailable (will use keyword fallback)",
            "local_cache": f"ok ({json_count} tweets)" if json_count > 0 else "empty - app 启动时自动从 Pinecone 同步",
        },
        "rag_features": {
            "qa_smart": "available" if all_ok else "unavailable",
            "qa_keyword": "available" if json_count > 0 else "unavailable",
            "trends": "available" if all_ok else "unavailable",
            "stats": "available" if pinecone_ok else "unavailable",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
