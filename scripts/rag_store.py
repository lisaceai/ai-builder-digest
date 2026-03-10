"""
RAG 向量存储模块
使用 ChromaDB + 智谱 Embedding 管理推文向量数据库
同时维护 JSON 文件存储，确保趋势分析和统计不依赖 ChromaDB
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from openai import OpenAI

try:
    import chromadb
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




def _filter_tweets_by_days(tweets, days=None):
    """按时间范围过滤推文列表"""
    if not days or not tweets:
        return tweets

    cutoff = datetime.utcnow() - timedelta(days=days)
    filtered = []
    for t in tweets:
        dt_str = t.get("metadata", {}).get("datetime", "")
        if not dt_str:
            filtered.append(t)
            continue

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

    return filtered


def ensure_vector_store_ready(db_path=None):
    """
    当向量库为空时，尝试使用 JSON 存储数据回填到 ChromaDB。
    返回 True 表示当前可用向量检索，False 表示不可用。
    """
    if not HAS_CHROMADB or not os.environ.get("ZHIPU_API_KEY", ""):
        return False

    try:
        collection = get_collection(db_path=db_path)
        if collection.count() > 0:
            return True

        records = _load_json_store()
        if not records:
            return False

        ids = [r["id"] for r in records if r.get("id") and r.get("document")]
        docs = [r["document"] for r in records if r.get("id") and r.get("document")]
        metas = [r.get("metadata", {}) for r in records if r.get("id") and r.get("document")]

        if not ids:
            return False

        embedding_client = get_embedding_client()
        batch_size = 20
        restored = 0
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i + batch_size]
            batch_docs = docs[i:i + batch_size]
            batch_meta = metas[i:i + batch_size]
            batch_embeddings = get_embeddings(batch_docs, client=embedding_client)
            collection.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
                embeddings=batch_embeddings,
            )
            restored += len(batch_ids)

        print(f"Hydrated ChromaDB from JSON store: {restored} tweets")
        return collection.count() > 0
    except Exception as e:
        print(f"Warning: failed to hydrate ChromaDB from JSON ({e})")
        return False


def get_all_vector_tweets(db_path=None, days=None):
    """从向量库读取全部推文（可按天数过滤）"""
    if not ensure_vector_store_ready(db_path=db_path):
        return []

    try:
        collection = get_collection(db_path=db_path)
        results = collection.get(include=["metadatas", "documents"])
        tweets = []
        for i, doc_id in enumerate(results.get("ids", [])):
            tweets.append({
                "id": doc_id,
                "document": results["documents"][i],
                "metadata": results["metadatas"][i],
            })
        return _filter_tweets_by_days(tweets, days=days)
    except Exception:
        return []

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
    当 ZHIPU_API_KEY 未设置或 ChromaDB 不可用时，仅保存到 JSON 文件
    """
    with open(tweets_file, "r", encoding="utf-8") as f:
        tweets = json.load(f)

    if not tweets:
        print("No tweets to ingest.")
        return 0

    # 准备数据
    all_tweet_records = []
    for t in tweets:
        tid = tweet_id_hash(t)
        summary = t.get("summary", "")
        text = t.get("text", "")
        doc = f"{summary}\n\n原文：{text}" if summary else text

        username = t.get("username", "unknown")
        dt = t.get("datetime", "")
        url = t.get("url", "")

        all_tweet_records.append({
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

    # 始终保存到 JSON 文件（确保数据不丢失）
    existing = _load_json_store()
    existing_ids = {t["id"] for t in existing}
    new_records = [r for r in all_tweet_records if r["id"] not in existing_ids]

    if not new_records:
        print("All tweets already in store.")
        return 0

    # 先写入 JSON（保底存储）
    print(f"Saving {len(new_records)} new tweets to JSON store...")
    existing.extend(new_records)
    _save_json_store(existing)
    ingested = len(new_records)
    print(f"Done. Total tweets in JSON store: {len(existing)}")

    # 尝试同时写入 ChromaDB（可选，用于向量搜索）
    use_chromadb = HAS_CHROMADB and os.environ.get("ZHIPU_API_KEY", "")
    if use_chromadb:
        try:
            collection = get_collection(db_path=db_path)
            embedding_client = get_embedding_client()

            chroma_existing_ids = set(collection.get()["ids"])
            chroma_new = [r for r in new_records if r["id"] not in chroma_existing_ids]

            if chroma_new:
                ids = [r["id"] for r in chroma_new]
                documents = [r["document"] for r in chroma_new]
                metadatas = [r["metadata"] for r in chroma_new]

                batch_size = 20
                chroma_ingested = 0
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
                    chroma_ingested += len(batch_ids)
                    print(f"  ChromaDB: {chroma_ingested}/{len(ids)} tweets")

                print(f"ChromaDB total: {collection.count()}")
        except Exception as e:
            print(f"Warning: ChromaDB ingestion failed ({e}), JSON store is still up to date.")

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
    优先使用向量检索（ChromaDB + embedding），不可用时自动降级为关键词匹配。
    """
    # 尝试向量检索
    vector_results = _search_vector(query, n_results, username, db_path)
    if vector_results:
        return vector_results

    # 降级：关键词匹配（不需要 API Key 或 ChromaDB）
    return _search_keyword(query, n_results, username)


def _search_vector(query, n_results=5, username=None, db_path=None):
    """向量检索（需要 ChromaDB + ZHIPU_API_KEY）"""
    if not ensure_vector_store_ready(db_path=db_path):
        return []

    collection = get_collection(db_path=db_path)
    if collection.count() == 0:
        return []

    try:
        embedding_client = get_embedding_client()
        query_embedding = get_embeddings([query], client=embedding_client)[0]
    except Exception:
        return []

    where_filter = {"username": username} if username else None

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


def _search_keyword(query, n_results=5, username=None):
    """关键词匹配降级方案（不需要 API Key 或 ChromaDB）"""
    all_tweets = _load_json_store()
    if not all_tweets:
        return []

    if username:
        all_tweets = [t for t in all_tweets if t.get("metadata", {}).get("username") == username]

    query_lower = query.lower()
    keywords = [w.strip() for w in query_lower.split() if len(w.strip()) > 1]

    scored = []
    for t in all_tweets:
        doc = (t.get("document", "") + " " + t.get("metadata", {}).get("summary", "")).lower()
        score = sum(1 for kw in keywords if kw in doc)
        if score > 0:
            scored.append((score, t))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, t in scored[:n_results]:
        results.append({
            "id": t.get("id", ""),
            "document": t.get("document", ""),
            "metadata": t.get("metadata", {}),
            "distance": 1.0 - (score / max(len(keywords), 1)),
        })

    return results


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
    优先从 ChromaDB 读取，fallback 到 JSON 文件
    days: 可选，只返回最近 N 天内的推文
    """
    tweets = []

    # 优先从 ChromaDB 读取
    if HAS_CHROMADB:
        try:
            collection = get_collection(db_path=db_path)
            if collection.count() > 0:
                results = collection.get(include=["metadatas", "documents"])
                for i, doc_id in enumerate(results["ids"]):
                    tweets.append({
                        "id": doc_id,
                        "document": results["documents"][i],
                        "metadata": results["metadatas"][i],
                    })
        except Exception:
            pass

    # ChromaDB 没有数据时，fallback 到 JSON
    if not tweets:
        tweets = _load_json_store()

    return _filter_tweets_by_days(tweets, days=days)


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
