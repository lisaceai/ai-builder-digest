"""
AI Summary Module
使用智谱GLM API生成推文摘要
"""

import os
import json
from openai import OpenAI


# 默认Prompt模板
SUMMARY_PROMPT = """你是一个AI技术推文分析师。请用1-2句话总结以下推文，要求：
1. 简洁明了，一句话概括核心内容
2. 保留关键信息（产品名、技术概念、观点）
3. 如果是对话/回复，尽量补充上下文背景

推文内容：
{tweet_text}

摘要："""


def generate_summary(tweet_text, api_key, model='glm-4.7-flash'):
    """生成单条推文的摘要"""
    if not tweet_text or not tweet_text.strip():
        return "（空推文）"

    client = OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4"
    )

    prompt = SUMMARY_PROMPT.format(tweet_text=tweet_text)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个专业的AI技术推文分析师，擅长用简洁的语言概括推文要点。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )

        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        print(f"Error generating summary: {e}")
        return "（摘要生成失败）"


def generate_summaries(tweets, api_key):
    """为所有推文生成摘要"""
    results = []

    for tweet in tweets:
        summary = generate_summary(tweet['text'], api_key)

        result = {
            'id': tweet.get('id', ''),
            'url': tweet.get('url', ''),
            'text': tweet.get('text', ''),
            'summary': summary,
            'username': tweet.get('username', ''),
            'datetime': tweet.get('datetime', '')
        }

        results.append(result)

    return results


if __name__ == '__main__':
    # 测试代码
    import sys

    if len(sys.argv) < 2:
        print("Usage: python summarize.py <input_file> [output_file]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'summarized_tweets.json'

    # 读取推文数据
    with open(input_file, 'r', encoding='utf-8') as f:
        tweets = json.load(f)

    # 获取API Key
    api_key = os.environ.get('ZHIPU_API_KEY', '')

    if not api_key:
        print("Error: ZHIPU_API_KEY not set")
        sys.exit(1)

    # 生成摘要
    print(f"Generating summaries for {len(tweets)} tweets...")
    results = generate_summaries(tweets, api_key)

    # 保存结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Summaries saved to {output_file}")
