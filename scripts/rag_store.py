"""
RAG 知识库模块
管理推文向量存储，支持语义搜索
"""

import os
import json
import math
from pathlib import Path
from openai import OpenAI

# 知识库文件路径
BASE_DIR = Path(__file__).resolve().parent.parent
KB_FILE = BASE_DIR / "data" / "knowledge_base.jsonl"


def get_client(api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4"
    )


def get_embedding(text: str, api_key: str) -> list[float]:
    """调用智谱 embedding-2 获取向量"""
    client = get_client(api_key)
    response = client.embeddings.create(
        model="embedding-2",
        input=text[:512]  # embedding-2 最大 512 tokens，截断保险
    )
    return response.data[0].embedding


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算余弦相似度"""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_knowledge_base() -> list[dict]:
    """读取知识库"""
    if not KB_FILE.exists():
        return []
    records = []
    with open(KB_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def save_knowledge_base(records: list[dict]) -> None:
    """保存知识库"""
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KB_FILE, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def add_tweets(tweets: list[dict], api_key: str) -> int:
    """
    将摘要推文列表加入知识库（去重）
    tweets: 来自 summarize.py 的输出，包含 id, url, text, summary, username, datetime
    返回新增条目数
    """
    existing = load_knowledge_base()
    existing_ids = {r["id"] for r in existing}

    new_records = []
    for tweet in tweets:
        tweet_id = str(tweet.get("id", ""))
        if not tweet_id or tweet_id in existing_ids:
            continue

        # 用摘要+原文作为 embedding 输入，覆盖更多语义
        embed_text = tweet.get("summary", "") or tweet.get("text", "")
        if not embed_text.strip():
            continue

        print(f"  Embedding tweet {tweet_id} (@{tweet.get('username', '')})...")
        try:
            embedding = get_embedding(embed_text, api_key)
        except Exception as e:
            print(f"  Warning: embedding failed for {tweet_id}: {e}")
            continue

        record = {
            "id": tweet_id,
            "url": tweet.get("url", ""),
            "text": tweet.get("text", ""),
            "summary": tweet.get("summary", ""),
            "username": tweet.get("username", ""),
            "datetime": tweet.get("datetime", ""),
            "embedding": embedding,
        }
        new_records.append(record)
        existing_ids.add(tweet_id)

    if new_records:
        save_knowledge_base(existing + new_records)
        print(f"Knowledge base: added {len(new_records)} new records (total {len(existing) + len(new_records)})")

    return len(new_records)


def search(query: str, api_key: str, top_k: int = 5) -> list[dict]:
    """
    语义搜索：返回与 query 最相关的 top_k 条推文
    返回列表中不含 embedding 字段
    """
    records = load_knowledge_base()
    if not records:
        return []

    query_embedding = get_embedding(query, api_key)

    scored = []
    for record in records:
        emb = record.get("embedding")
        if not emb:
            continue
        score = cosine_similarity(query_embedding, emb)
        scored.append((score, record))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, record in scored[:top_k]:
        result = {k: v for k, v in record.items() if k != "embedding"}
        result["score"] = round(score, 4)
        results.append(result)

    return results


def get_stats() -> dict:
    """返回知识库统计信息"""
    records = load_knowledge_base()
    if not records:
        return {"total": 0, "users": []}

    users = list({r.get("username", "") for r in records if r.get("username")})
    return {
        "total": len(records),
        "users": sorted(users),
    }
