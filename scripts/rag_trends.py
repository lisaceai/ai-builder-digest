"""
趋势分析模块
基于历史推文数据分析 AI 领域热点话题和趋势
"""

import os
import time
import logging
from datetime import timedelta
from openai import OpenAI
from scripts.rag_store import get_all_tweets_metadata, search_tweets, _load_json_store

logger = logging.getLogger(__name__)


TRENDS_SYSTEM_PROMPT = """你是一个 AI 技术趋势分析师，必须严格基于给定推文证据输出结论。

要求：
1. 不允许编造推文中未出现的事实、观点或 builder。
2. 每个热点话题后附上证据来源（@builder + 日期）。
3. 若证据不足，明确写“证据不足”。
4. 只总结输入推文中真实出现的信息。"""

TRENDS_PROMPT = """请基于以下 AI Builder 们最近的推文内容，分析当前 AI 领域的热点话题和趋势。

推文数据（共 {count} 条）：
{tweets_text}

请输出：
1. **热点话题**：列出 3-5 个当前最热门的话题，每个话题附带简短说明和相关 builder
2. **趋势洞察**：总结 1-2 个值得关注的技术趋势或方向
3. **Builder 动态**：简要说明哪些 builder 最活跃，他们在关注什么

用简洁自然的中文回答，适当使用 markdown 格式。"""

BUILDER_ANALYSIS_PROMPT = """请基于以下 @{username} 最近的推文内容，分析其关注方向和最近动态。

推文数据：
{tweets_text}

请总结：
1. 最近在关注什么话题
2. 有什么重要观点或发现
3. 推荐关注的重点内容

用简洁自然的中文回答。"""


def _check_api_key():
    """检查 API Key 是否已配置"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        raise ValueError("ZHIPU_API_KEY 环境变量未设置，无法进行分析。请在服务器环境中配置该密钥。")
    return api_key


def _get_llm_client():
    """获取 LLM 客户端"""
    api_key = _check_api_key()
    return OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        timeout=60.0,
    )


def _call_llm(system_prompt, user_prompt):
    """调用 LLM（带重试，最多 3 次，指数退避）"""
    client = _get_llm_client()
    last_err = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="glm-4.7",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                max_tokens=2000,
                extra_body={"thinking": {"type": "disabled"}},
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            if attempt < 2:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(f"Zhipu LLM call failed (attempt {attempt + 1}/3), retrying in {wait}s: {e}")
                time.sleep(wait)
    raise RuntimeError(f"Zhipu API 调用失败（已重试 3 次）: {last_err}")


# 趋势分析的通用语义查询词，用于向量搜索召回最有代表性的推文
TRENDS_SEARCH_QUERY = "AI technology trends products insights innovations"

def _fetch_tweets_by_vector(builders, per_builder, days=None):
    """
    用向量搜索按 builder 分别召回推文，通过 unix_timestamp 在 Pinecone 侧过滤时间范围。
    向量搜索不可用时返回空列表，外层降级为直接取本地数据。
    """
    from datetime import datetime, timezone
    since_ts = None
    if days:
        since_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    results = []
    for username in builders:
        hits = search_tweets(
            query=TRENDS_SEARCH_QUERY,
            n_results=per_builder,
            username=username,
            since_ts=since_ts,
        )
        results.extend(hits)
    return results


def analyze_trends(db_path=None, days=None):
    """
    分析整体趋势
    days: 可选，只分析最近 N 天的推文
    返回趋势分析文本
    """
    # 分析前尝试从 Pinecone 同步最新数据
    try:
        from scripts.rag_store import ensure_vector_store_ready
        ensure_vector_store_ready()
    except Exception:
        pass

    all_tweets = get_all_tweets_metadata(db_path=db_path, days=days)

    if not all_tweets:
        return {"analysis": "暂无推文数据，请先运行抓取流程导入推文。", "tweet_count": 0}

    # 时间范围内的 builder 列表
    builders = list({t.get("metadata", {}).get("username", "") for t in all_tweets if t.get("metadata", {}).get("username")})

    # per_builder 根据时间范围内实际数据动态计算：总条数 / builder 数，上限20条
    per_builder = max(5, min(20, len(all_tweets) // len(builders))) if builders else 10

    # 优先用向量搜索按 builder 召回推文，传入 days 做时间后置过滤
    sampled = _fetch_tweets_by_vector(builders, per_builder=per_builder, days=days)

    # 向量搜索无结果时降级为取本地最新120条
    if not sampled:
        sampled = sorted(all_tweets, key=lambda t: t.get("metadata", {}).get("datetime", ""), reverse=True)[:120]

    # 构建推文摘要文本（限制总长度）
    tweets_text_parts = []
    for t in sampled:
        meta = t.get("metadata", {})
        username = meta.get("username", "未知")
        dt = meta.get("datetime", "")
        summary = meta.get("summary", "")
        content = t.get("document", "")
        snippet = summary if summary else content[:280]
        if snippet:
            tweets_text_parts.append(f"@{username} ({dt}): {snippet}")

    tweets_text = "\n".join(tweets_text_parts)

    # 截断避免超长
    if len(tweets_text) > 8000:
        tweets_text = tweets_text[:8000] + "\n..."

    prompt = TRENDS_PROMPT.format(count=len(all_tweets), tweets_text=tweets_text)
    analysis = _call_llm(TRENDS_SYSTEM_PROMPT, prompt)

    return {
        "analysis": analysis,
        "tweet_count": len(all_tweets),
    }


def analyze_builder(username, db_path=None):
    """
    分析单个 Builder 的动态
    优先用向量检索，降级为直接从 JSON 按用户名过滤
    """
    results = search_tweets(
        query=f"@{username} 最近的推文和观点",
        n_results=20,
        username=username,
        db_path=db_path,
    )

    # 如果向量检索和关键词搜索都没结果，直接从 JSON 按用户名过滤
    if not results:
        all_tweets = get_all_tweets_metadata(db_path=db_path)
        results = [t for t in all_tweets if t.get("metadata", {}).get("username") == username][:20]

    if not results:
        return {
            "analysis": f"数据库中没有找到 @{username} 的推文数据。",
            "tweet_count": 0,
        }

    tweets_text_parts = []
    for r in results:
        meta = r.get("metadata", {})
        dt = meta.get("datetime", "")
        summary = meta.get("summary", "")
        content = r.get("document", "")
        snippet = summary if summary else content[:280]
        if snippet:
            tweets_text_parts.append(f"({dt}): {snippet}")

    tweets_text = "\n".join(tweets_text_parts)
    prompt = BUILDER_ANALYSIS_PROMPT.format(username=username, tweets_text=tweets_text)
    analysis = _call_llm(TRENDS_SYSTEM_PROMPT, prompt)

    return {
        "analysis": analysis,
        "tweet_count": len(results),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # 分析特定 builder
        result = analyze_builder(sys.argv[1])
        print(f"\n@{sys.argv[1]} 动态分析：")
    else:
        # 整体趋势分析
        result = analyze_trends()
        print("\n整体趋势分析：")

    print(f"\n{result['analysis']}")
    print(f"\n(基于 {result['tweet_count']} 条推文)")
