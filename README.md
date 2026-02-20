# AI Builder Daily Digest

每天自动抓取关注的AI builder推文，生成AI摘要并发送到邮箱。

## 功能

- 🤖 自动抓取指定用户的X推文
- 📝 AI生成摘要（使用智谱 GLM-4.6V）
- 📧 每天定时发送到邮箱
- ☁️ 基于GitHub Actions + Apify，无需服务器

## 快速开始

### 1. 配置Apify

1. 注册 [Apify](https://apify.com)
2. 使用现成的 Twitter Scraper Actor：`gentle_cloud~twitter-tweets-scraper`
3. 获取 API Token

### 2. 配置GitHub Secrets

在GitHub仓库的Settings > Secrets中添加以下 secrets：

| Secret | 说明 |
|--------|------|
| `APIFY_TOKEN` | Apify API Token |
| `ZHIPU_API_KEY` | 智谱AI API Key |
| `EMAIL_FROM` | 发件人邮箱 |
| `EMAIL_PASSWORD` | 邮箱密码或App密码 |
| `EMAIL_TO` | 收件人邮箱 |
| `EMAIL_SMTP_HOST` | SMTP服务器（默认smtp.gmail.com） |
| `EMAIL_SMTP_PORT` | SMTP端口（默认587） |

### 3. 配置用户列表

编辑 `config/users.json`，添加你想关注的AI builder用户名：

```json
{
  "ai_builders": [
    "sarah_chen_ai",
    "mranti",
    "builddaniel",
    "heyBarsee"
  ]
}
```

### 4. 启用GitHub Actions

推送代码到GitHub后，Actions会自动在每天UTC 2:30（北京时间10:30）运行。

也可以手动触发：进入Actions > Daily AI Builder Digest > Run workflow

## 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 测试摘要生成
python scripts/summarize.py sample_tweets.json

# 测试邮件发送
python scripts/send_email.py summarized_tweets.json
```

## 注意事项

- GitHub Actions每月有2000分钟免费额度
- Apify有免费credits，初期够用
- 智谱AI API按调用付费

## 文件结构

```
.
├── .github/
│   └── workflows/
│       └── daily-digest.yml
├── scripts/
│   ├── summarize.py       # AI摘要生成
│   └── send_email.py      # 邮件发送
├── config/
│   ├── users.json         # AI builder列表
│   └── settings.json      # 配置
├── templates/
│   └── email.html         # 邮件模板
└── requirements.txt
```

## 许可证

MIT
