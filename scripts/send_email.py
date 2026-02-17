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


def generate_email_content(tweets):
    """生成邮件内容"""
    template = load_email_template()

    cards = []
    for tweet in tweets:
        card = f"""
        <div class="card">
            <div class="username">@{tweet.get('username', 'unknown')}</div>
            <div class="summary">📝 {tweet.get('summary', '')}</div>
            <div class="original">原文: {tweet.get('text', '')[:200]}...</div>
            <a href="{tweet.get('url', '#')}" class="link">查看原文 →</a>
        </div>
        """
        cards.append(card)

    content = '\n'.join(cards)

    return template.format(
        date=datetime.now().strftime('%Y-%m-%d'),
        content=content,
        count=len(tweets)
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
