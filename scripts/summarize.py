"""
AI Summary Module
使用智谱GLM API生成推文摘要
"""

import os
import json
import time
from openai import OpenAI


# 默认Prompt模板
SUMMARY_PROMPT = """请用2-5句话概括以下推文的核心内容，像对朋友那样转述自然直接，不要逐字翻译，而是抓住重点，发生了什么，为什么重要

要求：
1. 只描述推文中明确提到的信息，必要时对文中的专有名词进行解释，不要臆想任何背景、解释或推测
2. 如果推文信息不足（如只有链接、只有图片、无实质内容），直接回复"信息不足，请查看推文原文"
3. 避免"该推文"、"作者""摘要"等词语
4. 不要用数字分点，保持自然叙述

推文内容：
{tweet_text}

概括："""


def extract_full_text(tweet):
    """提取完整的推文内容，包括转发和引用"""
    text = tweet.get('full_text') or tweet.get('text', '')

    # 处理转发 (retweeted_status)
    if 'retweeted_status' in tweet:
        rt = tweet['retweeted_status']
        rt_text = rt.get('full_text') or rt.get('text', '')
        # 用户可能添加了自己的评论
        if text.startswith('RT @'):
            # 纯转发，无个人评论
            text = rt_text
        else:
            # 转发+评论，保留用户评论 + 原文
            text = text + "\n\n转发原文：" + rt_text

    # 处理引用 (quoted_status)
    if 'quoted_status' in tweet:
        qt = tweet['quoted_status']
        qt_text = qt.get('full_text') or qt.get('text', '')
        text = text + "\n\n引用原文：" + qt_text

    return text.strip()


def generate_summary(tweet_text, api_key, model='glm-4.7'):
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
            temperature=0.5,
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
        # 使用 extract_full_text 提取完整推文内容（包括转发和引用）
        text = extract_full_text(tweet)
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
