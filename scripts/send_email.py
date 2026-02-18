"""
Email Sending Module
发送HTML格式的邮件
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def load_email_template():
    """加载邮件模板"""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'email.html')

    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()

    # 默认模板
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .card { background: #f9f9f9; border-radius: 10px; padding: 15px; margin-bottom: 15px; border-left: 4px solid #667eea; }
        .username { font-weight: bold; color: #667eea; }
        .summary { font-size: 15px; margin: 10px 0; }
        .original { font-size: 13px; color: #666; margin: 10px 0; padding: 10px; background: white; border-radius: 5px; }
        .link { display: inline-block; background: #667eea; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; font-size: 13px; }
        .footer { text-align: center; color: #999; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI Builder Daily</h1>
        <p>{date}</p>
    </div>

    {content}

    <div class="footer">
        <p>共 {count} 条推文 | AI Builder Digest</p>
    </div>
</body>
</html>"""


def find_sentence_boundary(text, max_length):
    """
    找到句子边界进行折叠
    如果max_length在句子中间，找到下一个句号/问号/感叹号位置
    """
    if len(text) <= max_length:
        return text, ""

    # 截取到指定长度
    truncated = text[:max_length]

    # 查找句子结束标志：。！？.!? 以及它们的组合
    sentence_endings = ['。', '！', '？', '.', '!', '?']
    last_end = -1

    # 从截断位置往后找句子边界
    for i in range(max_length, len(text)):
        if text[i] in sentence_endings:
            last_end = i
            break

    if last_end > max_length:
        # 找到了句子边界，在句子结束处折叠
        return text[:last_end+1], text[last_end+1:]
    else:
        # 没找到句子边界，直接在max_length处折叠
        return truncated, text[max_length:]


def generate_email_content(tweets):
    """生成邮件内容"""
    template = load_email_template()

    # 按作者分组
    authors = {}
    for tweet in tweets:
        author = tweet.get('username', 'unknown')
        if author not in authors:
            authors[author] = []
        authors[author].append(tweet)

    # 每组内按时间倒序（最新的在前）
    for author in authors:
        authors[author].sort(key=lambda t: t.get('datetime', ''), reverse=True)

    # 按作者名排序
    sorted_authors = sorted(authors.keys())

    cards = []
    for author in sorted_authors:
        author_tweets = authors[author]
        for tweet in author_tweets:
            # 原文超过350字折叠
            text = tweet.get('text', '')
            if len(text) > 350:
                # 智能找到句子边界进行折叠
                text_visible, text_hidden = find_sentence_boundary(text, 350)
                text_html = f'<div class="original">原文: {text_visible}<span style="color:#999;">（已折叠）</span></div>'
            else:
                text_html = f'<div class="original">原文: {text}</div>'

            # 格式化时间：月/日 小时:分，24小时制
            datetime_str = tweet.get('datetime', '')
            if datetime_str:
                datetime_clean = datetime_str.replace('Z', '').replace('+0000', '').strip()
                dt_part = datetime_clean.replace('T', ' ').split('.')[0] if datetime_clean else ''
                parts = dt_part.split(' ')
                if len(parts) >= 2:
                    # 格式: 02/18 14:30
                    date_part = parts[0][5:] if len(parts[0]) > 5 else parts[0]  # MM-DD
                    date_formatted = date_part.replace('-', '/')  # 改成 MM/DD
                    time_part = parts[1][:5]  # HH:MM
                    time_inline = f"{date_formatted} {time_part}"
                else:
                    time_inline = ''
            else:
                time_inline = ''

            # 使用用户名代替作者
            username = tweet.get('username', 'unknown')

            card = f'''
        <div class="card">
            <div class="username">@{username}</div>
            <div class="time">{time_inline}</div>
            <div class="summary">📝 {tweet.get('summary', '')}</div>
            {text_html}
            <a href="{tweet.get('url', '#')}" class="link" style="color:white;">查看原文</a>
        </div>'''
            cards.append(card)

    content = '\n'.join(cards)

    return template.replace(
        '{date}', datetime.now().strftime('%Y-%m-%d')
    ).replace(
        '{content}', content
    ).replace(
        '{count}', str(len(tweets))
    )


def send_email(
    smtp_host,
    smtp_port,
    sender_email,
    sender_password,
    recipient_email,
    subject,
    html_content
):
    """发送邮件"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    # 添加HTML内容
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)

    # 发送邮件
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)

    print(f"Email sent to {recipient_email}")


def main():
    """主函数"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python send_email.py <tweets_file>")
        sys.exit(1)

    tweets_file = sys.argv[1]

    # 读取推文数据
    with open(tweets_file, 'r', encoding='utf-8') as f:
        tweets = json.load(f)

    # 获取环境变量
    smtp_host = os.environ.get('EMAIL_SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
    sender_email = os.environ.get('EMAIL_FROM', '')
    sender_password = os.environ.get('EMAIL_PASSWORD', '')
    recipient_email = os.environ.get('EMAIL_TO', '')

    if not all([sender_email, sender_password, recipient_email]):
        print("Error: Missing email configuration")
        sys.exit(1)

    # 生成邮件内容
    html_content = generate_email_content(tweets)

    # 发送邮件
    subject = f"AI Builder Daily - {datetime.now().strftime('%Y-%m-%d')}"

    try:
        send_email(
            smtp_host,
            smtp_port,
            sender_email,
            sender_password,
            recipient_email,
            subject,
            html_content
        )
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
