"""
RAG 知识库摄入脚本
读取 summarized_tweets.json，将推文摘要存入知识库
在 GitHub Actions 中每日自动调用
"""

import os
import sys
import json

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(__file__))
from rag_store import add_tweets, get_stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python rag_ingest.py <summarized_tweets.json>")
        sys.exit(1)

    input_file = sys.argv[1]
    api_key = os.environ.get("ZHIPU_API_KEY", "")

    if not api_key:
        print("Error: ZHIPU_API_KEY not set")
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        tweets = json.load(f)

    print(f"Ingesting {len(tweets)} tweets into knowledge base...")
    added = add_tweets(tweets, api_key)
    stats = get_stats()
    print(f"Done. Added {added} new tweets. Knowledge base total: {stats['total']} records.")


if __name__ == "__main__":
    main()
