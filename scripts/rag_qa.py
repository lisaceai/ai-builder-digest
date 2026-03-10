"""
RAG 问答模块
基于向量检索的交互式问答
"""

import os
from openai import OpenAI
from scripts.rag_store import search_tweets, get_all_tweets_stats


QA_SYSTEM_PROMPT = """你是一个 AI 技术动态助手，基于 AI Builder 们的推文数据回答用户问题。

规则：
1. 只基于检索到的推文内容回答，不要编造信息
2. 如果检索结果中没有相关信息，诚实告知用户
3. 回答时注明信息来源（哪位 builder 说的）
4. 用简洁自然的中文回答
5. 如果涉及多位 builder 的观点，分别说明"""

QA_USER_PROMPT = """基于以下检索到的推文信息，回答用户的问题。

检索到的相关推文：
{context}

用户问题：{question}

请基于以上推文内容回答："""


def format_context(search_results):
    """将检索结果格式化为上下文文本"""
    parts = []
    for i, result in enumerate(search_results, 1):
        meta = result["metadata"]
        username = meta.get("username", "未知")
        dt = meta.get("datetime", "")
        url = meta.get("url", "")
        summary = meta.get("summary", "")
        text = result["document"]

        part = f"[{i}] @{username} ({dt})\n"
        if summary:
            part += f"摘要：{summary}\n"
        part += f"内容：{text[:500]}\n"
        if url:
            part += f"链接：{url}\n"
        parts.append(part)

    return "\n---\n".join(parts)


def ask(question, n_results=5, username=None, db_path=None):
    """
    RAG 问答
    question: 用户问题
    n_results: 检索结果数量
    username: 可选，只检索特定 builder 的推文
    """
    # 1. 检索相关推文（自动降级为关键词匹配）
    results = search_tweets(
        query=question,
        n_results=n_results,
        username=username,
        db_path=db_path,
    )

    if not results:
        stats = get_all_tweets_stats()
        total = stats.get("total_tweets", 0)

        if total > 0:
            return {
                "answer": "已检索到推文库中有数据，但没有找到与你问题直接相关的内容。你可以尝试：\n1. 换更短的关键词（如“RAG”“Agent”“开源模型”）\n2. 指定某位 Builder 再问\n3. 放宽问题范围后再提问",
                "sources": [],
            }

        return {
            "answer": "目前数据库中没有推文数据。请确保：\n1. 已运行 Daily Digest 工作流导入推文\n2. data/tweets_store.json 中有数据",
            "sources": [],
        }


    # 2. 构建上下文
    context = format_context(results)

    # 3. 调用 LLM 生成回答
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        # 无 API Key 时直接返回检索结果摘要
        summaries = []
        for r in results:
            meta = r["metadata"]
            summaries.append(f"@{meta.get('username', '未知')} ({meta.get('datetime', '')}): {meta.get('summary', r.get('document', '')[:200])}")
        return {
            "answer": "（ZHIPU_API_KEY 未配置，无法生成智能回答，以下为相关推文检索结果）\n\n" + "\n\n".join(summaries),
            "sources": [{"username": r["metadata"].get("username", ""), "datetime": r["metadata"].get("datetime", ""), "url": r["metadata"].get("url", ""), "summary": r["metadata"].get("summary", "")} for r in results],
        }

    client = OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4"
    )

    prompt = QA_USER_PROMPT.format(context=context, question=question)

    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
        extra_body={"thinking": {"type": "disabled"}},
    )

    answer = response.choices[0].message.content.strip()

    # 4. 构建来源列表
    sources = []
    for r in results:
        meta = r["metadata"]
        sources.append({
            "username": meta.get("username", ""),
            "datetime": meta.get("datetime", ""),
            "url": meta.get("url", ""),
            "summary": meta.get("summary", ""),
        })

    return {
        "answer": answer,
        "sources": sources,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.rag_qa '你的问题'")
        sys.exit(1)

    question = sys.argv[1]
    result = ask(question)
    print(f"\n问题：{question}")
    print(f"\n回答：{result['answer']}")
    print(f"\n来源：")
    for s in result["sources"]:
        print(f"  - @{s['username']} ({s['datetime']}): {s['url']}")
