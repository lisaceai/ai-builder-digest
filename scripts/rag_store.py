"""
RAG 向量存储模块
使用 JSON 文件 + 智谱 Embedding 实现轻量级向量检索
不依赖 ChromaDB，纯 Python 实现
"""

import os
import json
import math
import hashlib
from datetime import datetime
from openai import OpenAI


# JSON 存储路径
TWEETS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tweets_store.json")
EMBEDDINGS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "embeddings_store.json")


def get_embedding_client():
    """获取智谱 Embedding 客户端"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        raise ValueError("ZHIPU_API_KEY 环境变量未设置")
    return OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4"
    )


def get_embeddings(texts, client=None):
    """使用智谱 API 生成文本 embedding"""
    if client is None:
        client = get_embedding_client()

    embeddings = []
    for text in texts:
        truncated = text[:2000] if len(text) > 2000 else text
        response = client.embeddings.create(
            model="embedding-3",
            input=truncated
        )
        embeddings.append(response.data[0].embedding)
    return embeddings


def _cosine_similarity(a, b):
    """计算余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def tweet_id_hash(tweet):
    """生成推文的唯一 ID"""
    raw_id = tweet.get("id") or tweet.get("id_str", "")
    if raw_id:
        return str(raw_id)
    text = tweet.get("text", "") + tweet.get("username", "")
    return hashlib.md5(text.encode()).hexdigest()


def _load_json_store(json_path=None):
    """从 JSON 文件加载推文数据"""
    path = json_path or TWEETS_JSON_PATH
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_store(tweets, json_path=None):
    """保存推文数据到 JSON 文件"""
    path = json_path or TWEETS_JSON_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tweets, f, ensure_ascii=False, indent=2)


def _load_embeddings():
    """加载已缓存的 embedding"""
    if not os.path.exists(EMBEDDINGS_JSON_PATH):
        return {}
    with open(EMBEDDINGS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_embeddings(embeddings_map):
    """保存 embedding 缓存"""
    os.makedirs(os.path.dirname(EMBEDDINGS_JSON_PATH), exist_ok=True)
    with open(EMBEDDINGS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(embeddings_map, f)


def ingest_tweets(tweets_file, db_path=None):
    """
    将推文数据导入 JSON 存储并生成 embedding
    tweets_file: summarized_tweets.json 路径
    """
    with open(tweets_file, "r", encoding="utf-8") as f:
        tweets = json.load(f)

    if not tweets:
        print("No tweets to ingest.")
        return 0

    existing = _load_json_store()
    existing_ids = {t["id"] for t in existing}
    embeddings_map = _load_embeddings()
    embedding_client = get_embedding_client()

    new_count = 0
    for t in tweets:
        tid = tweet_id_hash(t)
        if tid in existing_ids:
            continue

        summary = t.get("summary", "")
        text = t.get("text", "")
        doc = f"{summary}\n\n原文：{text}" if summary else text

        username = t.get("username", "unknown")
        dt = t.get("datetime", "")
        url = t.get("url", "")

        # 生成 embedding
        emb = get_embeddings([doc], client=embedding_client)[0]
        embeddings_map[tid] = emb

        existing.append({
            "id": tid,
            "document": doc,
            "metadata": {
                "username": username,
                "datetime": dt,
                "url": url,
                "summary": summary,
                "original_text": text[:500],
            },
        })
        new_count += 1
        print(f"  Ingested {new_count} tweets...")

    _save_json_store(existing)
    _save_embeddings(embeddings_map)
    print(f"Done. Total tweets: {len(existing)}, new: {new_count}")
    return new_count


def search_tweets(query, n_results=5, username=None, db_path=None):
    """
    检索与查询相关的推文（余弦相似度）
    """
    tweets = _load_json_store()
    if not tweets:
        return []

    if username:
        tweets = [t for t in tweets if t.get("metadata", {}).get("username") == username]
    if not tweets:
        return []

    embeddings_map = _load_embeddings()

    # 没有 embedding 缓存时，退化为全量返回（首次使用时）
    if not embeddings_map:
        return [
            {"id": t["id"], "document": t["document"], "metadata": t["metadata"], "distance": 0.0}
            for t in tweets[:n_results]
        ]

    # 生成查询 embedding
    embedding_client = get_embedding_client()
    query_embedding = get_embeddings([query], client=embedding_client)[0]

    # 计算相似度并排序
    scored = []
    for t in tweets:
        tid = t["id"]
        if tid in embeddings_map:
            sim = _cosine_similarity(query_embedding, embeddings_map[tid])
        else:
            sim = -1.0
        scored.append((sim, t))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for sim, t in scored[:n_results]:
        results.append({
            "id": t["id"],
            "document": t["document"],
            "metadata": t["metadata"],
            "distance": 1.0 - sim if sim >= 0 else 2.0,
        })
    return results


def get_all_tweets_metadata(db_path=None, days=None):
    """获取所有推文的元数据（用于趋势分析）"""
    tweets = _load_json_store()

    if days and tweets:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        filtered = []
        for t in tweets:
            dt_str = t.get("metadata", {}).get("datetime", "")
            if dt_str:
                try:
                    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
                        try:
                            dt = datetime.strptime(dt_str[:26], fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        filtered.append(t)
                        continue
                    if dt >= cutoff:
                        filtered.append(t)
                except Exception:
                    filtered.append(t)
            else:
                filtered.append(t)
        tweets = filtered

    return tweets


def get_all_tweets_stats(days=None):
    """获取推文统计"""
    tweets = get_all_tweets_metadata(days=days)
    builder_counts = {}
    for t in tweets:
        username = t.get("metadata", {}).get("username", "unknown")
        builder_counts[username] = builder_counts.get(username, 0) + 1
    return {
        "total_tweets": len(tweets),
        "builder_counts": builder_counts,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python rag_store.py <summarized_tweets.json>")
        sys.exit(1)

    count = ingest_tweets(sys.argv[1])
    print(f"Ingested {count} tweets.")
