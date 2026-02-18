"""
AI Summary Module
使用智谱GLM API生成推文摘要
"""

import os
import json
import time
from openai import OpenAI


# 默认Prompt模板
SUMMARY_PROMPT = """请用5句话左右总结以下推文，直接给出简洁的摘要，不要有任何思考过程、步骤说明或格式。不要出现"作者"两个字，不要用数字分点。

要求：
1. 保留关键信息（产品名称、技术概念、观点）
2. 如果是对话/回复，尽量补充上下文背景
3. 避免"该推文"、该作者"、摘要："等词语

推文内容：
{tweet_text}

摘要："""


def generate_summary(tweet_text, api_key, model='glm-4.6V'):
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
            max_tokens=800,
            # 禁用思考模型，强制直接输出
            extra_body={
                "thinking": {
                    "type": "disabled"
                }
            }
        )

        summary = response.choices[0].message.content.strip()
        # 如果 content 为空，尝试使用 reasoning_content
        if not summary and hasattr(response.choices[0].message, 'reasoning_content'):
            summary = response.choices[0].message.reasoning_content.strip()
        print(f"Generated summary: {summary[:50]}...")  # 添加日志
        return summary

    except Exception as e:
        print(f"Error generating summary: {e}")
        import traceback
        traceback.print_exc()
        return f"（摘要生成失败: {str(e)}）"


def generate_summaries(tweets, api_key):
    """为所有推文生成摘要"""
    results = []

    print(f"Processing {len(tweets)} tweets...")

    for i, tweet in enumerate(tweets):
        # 处理不同 actor 返回的字段名
        text = tweet.get('full_text') or tweet.get('text', '')
        print(f"Tweet {i+1}: {text[:80]}...")  # 添加日志

        # 获取用户名
        username = ''
        if 'user' in tweet:
            user = tweet.get('user', {})
            if 'legacy' in user:
                username = user['legacy'].get('screen_name', '')
            else:
                username = user.get('screen_name', '')
        else:
            username = tweet.get('username', '')

        # 获取时间
        datetime = tweet.get('created_at', '') or tweet.get('datetime', '')

        # 获取URL
        url = tweet.get('url', '')

        summary = generate_summary(text, api_key)

        # 添加延迟避免速率限制
        time.sleep(1)

        result = {
            'id': tweet.get('id', tweet.get('id_str', '')),
            'url': url,
            'text': text,
            'summary': summary,
            'username': username,
            'datetime': datetime
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
