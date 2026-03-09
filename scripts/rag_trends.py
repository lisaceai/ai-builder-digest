"""
趋势分析模块
基于历史推文数据分析 AI 领域热点话题和趋势
"""

import os
from openai import OpenAI
from scripts.rag_store import get_all_tweets_metadata, search_tweets


TRENDS_SYSTEM_PROMPT = """你是一个 AI 技术趋势分析师，擅长从推文数据中发现技术趋势和热点话题。"""

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
        base_url="https://open.bigmodel.cn/api/paas/v4"
    )


def _call_llm(system_prompt, user_prompt):
    """调用 LLM"""
    client = _get_llm_client()
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


def analyze_trends(db_path=None, days=None):
    """
    分析整体趋势
    days: 可选，只分析最近 N 天的推文
    返回趋势分析文本
    """
    all_tweets = get_all_tweets_metadata(db_path=db_path, days=days)

    if not all_tweets:
        return {"analysis": "数据库中暂无推文数据，请先导入推文。", "tweet_count": 0}

    # 构建推文摘要文本（限制总长度）
    tweets_text_parts = []
    for t in all_tweets[:100]:  # 最多分析 100 条
        meta = t["metadata"]
        username = meta.get("username", "未知")
        dt = meta.get("datetime", "")
        summary = meta.get("summary", "")
        if summary:
            tweets_text_parts.append(f"@{username} ({dt}): {summary}")

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
    """
    results = search_tweets(
        query=f"@{username} 最近的推文和观点",
        n_results=20,
        username=username,
        db_path=db_path,
    )

    if not results:
        return {
            "analysis": f"数据库中没有找到 @{username} 的推文数据。",
            "tweet_count": 0,
        }

    tweets_text_parts = []
    for r in results:
        meta = r["metadata"]
        dt = meta.get("datetime", "")
        summary = meta.get("summary", "")
        if summary:
            tweets_text_parts.append(f"({dt}): {summary}")

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
