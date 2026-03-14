"""
RAG 向量存储模块
使用 Pinecone + 智谱 Embedding 管理推文向量数据库
本地 JSON 作为运行时缓存（启动时从 Pinecone 同步），不再提交到 git
"""

import os
import json
import hashlib
import re
from datetime import datetime, timedelta
from openai import OpenAI

try:
    from pinecone import Pinecone, ServerlessSpec
    HAS_PINECONE = True
except ImportError:
    HAS_PINECONE = False


# JSON 存储路径（不依赖 Pinecone）
TWEETS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tweets_store.json")

# Pinecone 配置
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "tweets")
EMBEDDING_DIM = 2048  # 智谱 embedding-3 维度


def get_embedding_client():
    """获取智谱 Embedding 客户端"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        raise ValueError("ZHIPU_API_KEY 环境变量未设置")
    return OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        timeout=8.0,  # embedding 快速超时，失败后降级关键词搜索
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


def get_pinecone_index():
    """获取 Pinecone 索引（不存在则自动创建）"""
    if not HAS_PINECONE:
        raise ImportError("pinecone 未安装，请运行 pip install pinecone")
    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        raise ValueError("PINECONE_API_KEY 环境变量未设置")

    pc = Pinecone(api_key=api_key)
    index_name = PINECONE_INDEX_NAME

    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    return pc.Index(index_name)


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


def _sync_from_pinecone():
    """从 Pinecone 全量拉取所有推文 metadata，写入本地 JSON 缓存。返回同步条数。"""
    index = get_pinecone_index()

    # list() 返回 ID 分页生成器
    all_ids = []
    for ids_page in index.list():
        all_ids.extend(ids_page)

    if not all_ids:
        return 0

    tweets = []
    for i in range(0, len(all_ids), 1000):
        batch_ids = all_ids[i:i + 1000]
        result = index.fetch(ids=batch_ids)
        for vid, vec in result.vectors.items():
            meta = dict(vec.metadata or {})
            tweets.append({
                "id": vid,
                "document": meta.get("document", ""),
                "metadata": meta,
            })

    _save_json_store(tweets)
    print(f"Synced {len(tweets)} tweets from Pinecone to local cache")
    return len(tweets)


def ensure_vector_store_ready():
    """
    启动时将 Pinecone 数据同步到本地 JSON 缓存（供趋势分析/关键词搜索使用）。
    本地缓存条数 < Pinecone 时触发全量同步。
    返回 True 表示 Pinecone 可用，False 表示不可用。
    """
    if not HAS_PINECONE or not os.environ.get("PINECONE_API_KEY", ""):
        return False

    try:
        index = get_pinecone_index()
        pinecone_count = index.describe_index_stats().total_vector_count

        if pinecone_count == 0:
            return False

        local_count = len(_load_json_store())
        if local_count >= pinecone_count:
            print(f"Local cache up to date ({local_count} tweets)")
            return True

        print(f"Local cache ({local_count}) behind Pinecone ({pinecone_count}), syncing...")
        synced = _sync_from_pinecone()
        return synced > 0
    except Exception as e:
        print(f"Warning: failed to sync from Pinecone ({e})")
        return False


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
    将推文数据导入 Pinecone 向量数据库
    tweets_file: summarized_tweets.json 路径
    当 PINECONE_API_KEY/ZHIPU_API_KEY 未设置或 Pinecone 不可用时，仅保存到 JSON 文件
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

        username = t.get("username", "unknown").lower().strip()
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
                "document": doc,  # 冗余存储，Pinecone 查询时可还原
            },
        })

    # 更新本地 JSON 缓存（运行时使用，非持久化存储）
    existing = _load_json_store()
    existing_ids = {t["id"] for t in existing}
    new_records = [r for r in all_tweet_records if r["id"] not in existing_ids]

    if not new_records:
        print("All tweets already in store.")
        return 0

    existing.extend(new_records)
    _save_json_store(existing)
    ingested = len(new_records)
    print(f"New tweets: {ingested}, local cache total: {len(existing)}")

    # 尝试同时写入 Pinecone（可选，用于向量搜索）
    use_pinecone = HAS_PINECONE and os.environ.get("PINECONE_API_KEY", "") and os.environ.get("ZHIPU_API_KEY", "")
    if use_pinecone:
        try:
            index = get_pinecone_index()
            embedding_client = get_embedding_client()

            ids = [r["id"] for r in new_records]
            documents = [r["document"] for r in new_records]
            metadatas = [r["metadata"] for r in new_records]

            batch_size = 20
            pinecone_ingested = 0
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i + batch_size]
                batch_docs = documents[i:i + batch_size]
                batch_meta = metadatas[i:i + batch_size]
                batch_embeddings = get_embeddings(batch_docs, client=embedding_client)
                vectors = [
                    {"id": vid, "values": emb, "metadata": meta}
                    for vid, emb, meta in zip(batch_ids, batch_embeddings, batch_meta)
                ]
                index.upsert(vectors=vectors)
                pinecone_ingested += len(batch_ids)
                print(f"  Pinecone: {pinecone_ingested}/{len(ids)} tweets")

            stats = index.describe_index_stats()
            print(f"Pinecone total: {stats.total_vector_count}")
        except Exception as e:
            print(f"Warning: Pinecone ingestion failed ({e}), JSON store is still up to date.")

    return ingested


def search_tweets(query, n_results=5, username=None, db_path=None):
    """
    检索与查询相关的推文
    优先使用向量检索（Pinecone + embedding），不可用时自动降级为关键词匹配。
    """
    vector_results = _search_vector(query, n_results, username)
    if vector_results:
        return vector_results

    # 降级：关键词匹配
    return _search_keyword(query, n_results, username)


def _search_vector(query, n_results=5, username=None):
    """向量检索（需要 Pinecone + ZHIPU_API_KEY）"""
    if not HAS_PINECONE or not os.environ.get("PINECONE_API_KEY", "") or not os.environ.get("ZHIPU_API_KEY", ""):
        return []

    try:
        index = get_pinecone_index()
        embedding_client = get_embedding_client()
        query_embedding = get_embeddings([query], client=embedding_client)[0]
    except Exception:
        return []

    where_filter = {"username": {"$eq": username}} if username else None

    try:
        results = index.query(
            vector=query_embedding,
            top_k=n_results,
            filter=where_filter,
            include_metadata=True,
        )
    except Exception:
        return []

    # 相关性阈值：指定用户时降低阈值（已按人过滤，语义门槛可放宽）
    SCORE_THRESHOLD = 0.3 if username else 0.55
    tweets = []
    for match in results.matches:
        if match.score < SCORE_THRESHOLD:
            continue
        meta = match.metadata or {}
        # 后置校验：防止 Pinecone filter 失效时混入其他 builder 的推文
        if username and meta.get("username", "").lower() != username.lower():
            continue
        tweets.append({
            "id": match.id,
            "document": meta.get("document") or meta.get("summary", "") or meta.get("original_text", ""),
            "metadata": meta,
            "distance": 1.0 - match.score,
        })

    return tweets


def _extract_keywords(query):
    """提取查询关键词，兼容中英文与无空格中文提问。"""
    query_lower = (query or "").lower().strip()
    if not query_lower:
        return []

    # 先提取中英文词块
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_#@.-]{2,}", query_lower)

    # 对纯中文长句补充 2-4 字子串，提升无空格中文检索召回
    cjk_only = re.sub(r"[^\u4e00-\u9fff]", "", query_lower)
    if len(cjk_only) >= 4:
        for n in (2, 3, 4):
            if len(cjk_only) >= n:
                tokens.extend(cjk_only[i:i+n] for i in range(0, len(cjk_only) - n + 1))

    # 去重并过滤停用词
    stop_words = {"最近", "什么", "哪些", "怎么", "一下", "关于", "以及", "这个", "那个", "分析", "趋势"}
    seen = set()
    keywords = []
    for t in tokens:
        if t in stop_words or len(t) < 2:
            continue
        if t not in seen:
            seen.add(t)
            keywords.append(t)
    return keywords


def _search_keyword(query, n_results=5, username=None):
    """关键词匹配降级方案（不需要 API Key 或 Pinecone）"""
    all_tweets = _load_json_store()
    if not all_tweets:
        return []

    if username:
        all_tweets = [t for t in all_tweets if t.get("metadata", {}).get("username", "").lower() == username.lower()]

    keywords = _extract_keywords(query)

    scored = []
    if keywords:
        for t in all_tweets:
            doc = (t.get("document", "") + " " + t.get("metadata", {}).get("summary", "")).lower()
            score = 0
            for kw in keywords:
                if kw in doc:
                    # 长关键词权重更高
                    score += 2 if len(kw) >= 4 else 1
            if score > 0:
                scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)

    # 指定用户但关键词匹配无结果时，兜底返回该用户最近 N 条推文
    if username and not scored:
        def _parse_dt(t):
            dt_str = t.get("metadata", {}).get("datetime", "")
            for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(dt_str[:26], fmt)
                except ValueError:
                    continue
            return datetime.min

        recent = sorted(all_tweets, key=_parse_dt, reverse=True)[:n_results]
        return [
            {"id": t.get("id", ""), "document": t.get("document", ""), "metadata": t.get("metadata", {}), "distance": 0.5}
            for t in recent
        ]

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
    从 JSON 文件读取（Pinecone 不支持全量扫描）
    days: 可选，只返回最近 N 天内的推文
    """
    tweets = _load_json_store()
    return _filter_tweets_by_days(tweets, days=days)


def get_all_tweets_stats(days=None):
    """获取推文统计（不依赖 Pinecone）"""
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
    print(f"Ingested {count} tweets into Pinecone.")
