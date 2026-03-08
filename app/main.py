from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import os
import sys
import subprocess
from pathlib import Path

# 确保 scripts 目录可导入
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from rag_store import search, get_stats

app = FastAPI(title="AI Builder 管理器")

# 配置路径
CONFIG_FILE = BASE_DIR / "config" / "users.json"

RAG_PROMPT = """你是 AI Builder 动态助手，专门回答关于 AI 创业者最新动态的问题。

以下是从知识库中检索到的相关推文摘要（按相关度排列）：

{context}

请根据以上内容，用中文简洁地回答用户的问题。
- 只基于检索到的内容作答，不要编造信息
- 如果检索内容与问题无关，请如实告知
- 可以引用具体的人名和推文内容，增加可信度
- 回答要自然流畅，不要逐条列举

用户问题：{question}"""


class UsersData(BaseModel):
    ai_builders: list[str]


class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]


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


@app.get("/api/kb/stats")
async def kb_stats():
    """知识库统计信息"""
    return get_stats()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """RAG 问答接口"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="ZHIPU_API_KEY 未配置")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 语义检索相关推文
    try:
        sources = search(question, api_key, top_k=req.top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")

    if not sources:
        return ChatResponse(
            answer="知识库暂无内容，请等待每日摘要任务运行后再试。",
            sources=[]
        )

    # 构建上下文
    context_parts = []
    for i, src in enumerate(sources, 1):
        username = src.get("username", "未知")
        summary = src.get("summary", src.get("text", ""))
        dt = src.get("datetime", "")
        context_parts.append(f"[{i}] @{username} ({dt[:10] if dt else ''}): {summary}")

    context = "\n".join(context_parts)
    prompt = RAG_PROMPT.format(context=context, question=question)

    # 调用 LLM 生成答案
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4"
        )
        response = client.chat.completions.create(
            model="glm-4.7",
            messages=[
                {"role": "system", "content": "你是 AI Builder 动态助手，基于推文知识库回答用户问题。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
            extra_body={"thinking": {"type": "disabled"}}
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成回答失败: {e}")

    return ChatResponse(answer=answer, sources=sources)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
