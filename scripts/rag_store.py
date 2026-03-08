"""
RAG 向量存储模块
使用 ChromaDB + 智谱 Embedding 管理推文向量数据库
同时维护 JSON 文件存储，确保趋势分析和统计不依赖 ChromaDB
"""

import os
import json
import hashlib
from datetime import datetime
from openai import OpenAI

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


# ChromaDB 持久化路径
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_db")

# JSON 存储路径（不依赖 ChromaDB）
TWEETS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tweets_store.json")


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
        # 截断过长文本
        truncated = text[:2000] if len(text) > 2000 else text
        response = client.embeddings.create(
            model="embedding-3",
            input=truncated
        )
        embeddings.append(response.data[0].embedding)
    return embeddings


def get_chroma_client(db_path=None):
    """获取 ChromaDB 持久化客户端"""
    if not HAS_CHROMADB:
        raise ImportError("chromadb 未安装，请运行 pip install chromadb")
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path)


def get_collection(client=None, db_path=None):
    """获取或创建推文集合"""
    if client is None:
        client = get_chroma_client(db_path)
    return client.get_or_create_collection(
        name="tweets",
        metadata={"description": "AI Builder 推文向量集合"}
    )


def tweet_id_hash(tweet):
    """生成推文的唯一 ID"""
    raw_id = tweet.get("id") or tweet.get("id_str", "")
    if raw_id:
        return str(raw_id)
    # fallback: 用内容 hash
    text = tweet.get("text", "") + tweet.get("username", "")
    return hashlib.md5(text.encode()).hexdigest()


def ingest_tweets(tweets_file, db_path=None):
    """
    将推文数据导入 ChromaDB 向量数据库
    tweets_file: summarized_tweets.json 路径
    """
    with open(tweets_file, "r", encoding="utf-8") as f:
        tweets = json.load(f)

    if not tweets:
        print("No tweets to ingest.")
        return 0

    collection = get_collection(db_path=db_path)
    embedding_client = get_embedding_client()

    # 过滤掉已存在的推文
    existing_ids = set(collection.get()["ids"])
    new_tweets = []
    for t in tweets:
        tid = tweet_id_hash(t)
        if tid not in existing_ids:
            new_tweets.append(t)

    if not new_tweets:
        print("All tweets already in database.")
        return 0

    print(f"Ingesting {len(new_tweets)} new tweets...")

    # 准备数据
    ids = []
    documents = []
    metadatas = []

    for t in new_tweets:
        tid = tweet_id_hash(t)
        # 将摘要和原文合并为文档内容，便于检索
        summary = t.get("summary", "")
        text = t.get("text", "")
        doc = f"{summary}\n\n原文：{text}" if summary else text

        username = t.get("username", "unknown")
        dt = t.get("datetime", "")
        url = t.get("url", "")

        ids.append(tid)
        documents.append(doc)
        metadatas.append({
            "username": username,
            "datetime": dt,
            "url": url,
            "summary": summary,
            "original_text": text[:500],  # 限制长度
        })

    # 批量生成 embedding 并入库（每批 20 条）
    batch_size = 20
    ingested = 0
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_docs = documents[i:i + batch_size]
        batch_meta = metadatas[i:i + batch_size]

        batch_embeddings = get_embeddings(batch_docs, client=embedding_client)

        collection.add(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_meta,
            embeddings=batch_embeddings,
        )
        ingested += len(batch_ids)
        print(f"  Ingested {ingested}/{len(ids)} tweets")

    print(f"Done. Total tweets in DB: {collection.count()}")

    # 同步保存到 JSON 文件（确保趋势分析和统计不依赖 ChromaDB）
    _sync_to_json(collection)

    return ingested


def _sync_to_json(collection):
    """将 ChromaDB 数据同步到 JSON 文件"""
    try:
        results = collection.get(include=["metadatas", "documents"])
        tweets = []
        for i, doc_id in enumerate(results["ids"]):
            tweets.append({
                "id": doc_id,
                "document": results["documents"][i],
                "metadata": results["metadatas"][i],
            })
        _save_json_store(tweets)
        print(f"Synced {len(tweets)} tweets to {TWEETS_JSON_PATH}")
    except Exception as e:
        print(f"Warning: Failed to sync to JSON: {e}")


def search_tweets(query, n_results=5, username=None, db_path=None):
    """
    检索与查询相关的推文
    query: 自然语言查询
    n_results: 返回结果数量
    username: 可选，按作者过滤
    """
    collection = get_collection(db_path=db_path)
    embedding_client = get_embedding_client()

    query_embedding = get_embeddings([query], client=embedding_client)[0]

    where_filter = None
    if username:
        where_filter = {"username": username}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"]
    )

    tweets = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            tweets.append({
                "id": doc_id,
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

    return tweets


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


def get_all_tweets_metadata(db_path=None, days=None):
    """
    获取所有推文的元数据（用于趋势分析）
    优先从 JSON 文件读取，fallback 到 ChromaDB
    days: 可选，只返回最近 N 天内的推文
    """
    tweets = _load_json_store()

    if not tweets and HAS_CHROMADB:
        try:
            collection = get_collection(db_path=db_path)
            results = collection.get(include=["metadatas", "documents"])
            for i, doc_id in enumerate(results["ids"]):
                tweets.append({
                    "id": doc_id,
                    "document": results["documents"][i],
                    "metadata": results["metadatas"][i],
                })
        except Exception:
            pass

    # 按时间范围过滤
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
    """
    获取推文统计（不依赖 ChromaDB）
    """
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
    print(f"Ingested {count} tweets into ChromaDB.")
