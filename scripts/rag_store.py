"""
RAG 向量存储模块
使用纯 JSON 文件存储 + 内存 TF-IDF 向量搜索，无需外部向量数据库或 Embedding API
"""

import os
import re
import json
import math
import hashlib
from datetime import datetime, timedelta
from collections import Counter


# JSON 存储路径
TWEETS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tweets_store.json")


def tweet_id_hash(tweet):
    """生成推文的唯一 ID"""
    raw_id = tweet.get("id") or tweet.get("id_str", "")
    if raw_id:
        return str(raw_id)
    # fallback: 用内容 hash
    text = tweet.get("text", "") + tweet.get("username", "")
    return hashlib.md5(text.encode()).hexdigest()


def _tokenize(text):
    """简单分词：提取英文单词和中文单字"""
    return re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]', text.lower())


def _build_tfidf(documents):
    """构建 TF-IDF 向量"""
    doc_tokens = [_tokenize(doc) for doc in documents]
    df = Counter()
    for tokens in doc_tokens:
        for term in set(tokens):
            df[term] += 1

    n_docs = len(documents)
    tfidf_vectors = []
    for tokens in doc_tokens:
        tf = Counter(tokens)
        total = len(tokens) if tokens else 1
        vec = {}
        for term, count in tf.items():
            idf = math.log((n_docs + 1) / (df[term] + 1)) + 1
            vec[term] = (count / total) * idf
        tfidf_vectors.append(vec)

    return tfidf_vectors


def _cosine_similarity(vec_a, vec_b):
    """计算两个稀疏向量的余弦相似度"""
    common_terms = set(vec_a.keys()) & set(vec_b.keys())
    if not common_terms:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in common_terms)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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


def ingest_tweets(tweets_file, db_path=None):
    """
    将推文数据导入 JSON 存储
    tweets_file: summarized_tweets.json 路径
    不需要外部 API Key
    """
    with open(tweets_file, "r", encoding="utf-8") as f:
        tweets = json.load(f)

    if not tweets:
        print("No tweets to ingest.")
        return 0

    existing = _load_json_store(db_path)
    existing_ids = {t["id"] for t in existing}

    new_entries = []
    for t in tweets:
        tid = tweet_id_hash(t)
        if tid in existing_ids:
            continue

        summary = t.get("summary", "")
        text = t.get("text", "")
        doc = f"{summary}\n\n原文：{text}" if summary else text

        new_entries.append({
            "id": tid,
            "document": doc,
            "metadata": {
                "username": t.get("username", "unknown"),
                "datetime": t.get("datetime", ""),
                "url": t.get("url", ""),
                "summary": summary,
                "original_text": text[:500],
            },
        })

    if not new_entries:
        print("All tweets already in database.")
        return 0

    print(f"Ingesting {len(new_entries)} new tweets...")
    all_tweets = existing + new_entries
    _save_json_store(all_tweets, db_path)
    print(f"Done. Total tweets in store: {len(all_tweets)}")
    return len(new_entries)


def search_tweets(query, n_results=5, username=None, db_path=None):
    """
    使用 TF-IDF 内存向量搜索检索相关推文
    query: 自然语言查询
    n_results: 返回结果数量
    username: 可选，按作者过滤
    """
    tweets = _load_json_store(db_path)

    if not tweets:
        return []

    if username:
        tweets = [t for t in tweets if t.get("metadata", {}).get("username") == username]

    if not tweets:
        return []

    documents = [t["document"] for t in tweets]
    all_docs = documents + [query]

    tfidf_vectors = _build_tfidf(all_docs)
    query_vec = tfidf_vectors[-1]
    doc_vecs = tfidf_vectors[:-1]

    scored = []
    for i, doc_vec in enumerate(doc_vecs):
        sim = _cosine_similarity(query_vec, doc_vec)
        scored.append((sim, i))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for sim, idx in scored[:n_results]:
        if sim > 0:
            t = tweets[idx]
            results.append({
                "id": t["id"],
                "document": t["document"],
                "metadata": t["metadata"],
                "distance": 1.0 - sim,
            })

    return results


def get_all_tweets_metadata(db_path=None, days=None):
    """
    获取所有推文的元数据（用于趋势分析）
    days: 可选，只返回最近 N 天内的推文
    """
    tweets = _load_json_store(db_path)

    if days and tweets:
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
    print(f"Ingested {count} tweets into store.")
