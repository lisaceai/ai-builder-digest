# AI Builder Daily Digest

每天自动抓取关注的AI builder推文，生成AI摘要并发送到邮箱。

## 功能

- 🤖 自动抓取指定用户的X推文
- 📝 AI生成摘要（使用智谱 GLM-4.6V）
- 📧 每天定时发送到邮箱
- ☁️ 基于GitHub Actions + Apify，无需服务器
- 🌐 Web界面管理关注的 Builder 列表

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

## 本地 Web 管理界面

启动本地服务管理关注的 Builder 列表：

```bash
# 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

然后访问 http://localhost:8000 （同一局域网设备可用电脑 IP 访问）

保存后会自动推送到 GitHub，触发新的抓取任务。

## RAG 智能问答与趋势分析

Web 界面包含三大功能：

- **RAG 问答** - 基于历史推文的智能问答（支持按 Builder 过滤）
- **趋势分析** - AI 领域热点话题洞察（可选时间范围）
- **Builder 管理** - 管理关注的 AI Builder 列表

### RAG 部署配置

RAG 功能需要以下条件：

1. **`ZHIPU_API_KEY`** - 必须在部署环境中设置（Render Dashboard > Environment）
2. **推文数据** - 需要至少运行一次 Daily Digest 工作流，数据保存在 `data/tweets_store.json`
3. **ChromaDB**（可选）- 用于向量检索，不可用时自动降级为关键词匹配


### 常见问题：ChromaDB 需要单独注册吗？

不需要。这个项目使用的是 **本地持久化 ChromaDB**（Python 包 `chromadb`），程序会自动在 `data/chroma_db` 创建和读写向量库，无需登录或在 Chroma 官网做任何初始化。

如果你看到“RAG 无数据 / 趋势分析为 0”，通常不是 Chroma 注册问题，而是以下任一项未满足：

1. `data/tweets_store.json` 为空（需要先跑 Daily Digest 导入推文）
2. 部署环境未设置 `ZHIPU_API_KEY`（影响智能问答与趋势分析）

建议先访问 `/api/health` 检查：
- `json_store` 是否为 `ok (...)`
- `zhipu_api_key` 是否为 `configured`
- `chromadb` 即使显示 unavailable 也可走关键词降级，不是阻塞项

### 检查部署状态

访问 `/api/health` 可查看各组件配置状态：
- `zhipu_api_key`: API 密钥是否配置
- `json_store`: 推文数据是否已导入
- `chromadb`: 向量数据库是否可用

### Render 部署

```bash
# render.yaml 已配置，直接连接 GitHub 仓库即可
# 重要：在 Render Dashboard 中设置 ZHIPU_API_KEY 环境变量
```

### 本地开发

```bash
# 1. 复制环境变量
cp .env.example .env
# 2. 编辑 .env，填入你的 ZHIPU_API_KEY
# 3. 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Render 常见误区：需要在 Render 上 manual commit 吗？

不需要。Render 上部署的是 GitHub 仓库代码快照，你**不需要也不应该**在 Render 实例里手动 commit。

正确流程是：
1. Daily Digest GitHub Actions 抓取并更新 `data/tweets_store.json`
2. Workflow 自动 commit 并 push 到 `main`
3. Render 监听到 `main` 新提交后自动重新部署

如果你在 Render 里看到 RAG 仍是 0，通常是：
- GitHub Actions 没有成功跑完；或
- Workflow 没有成功 push 到 `main`；或
- Render 没触发自动部署（可在 Render 面板点一次 Manual Deploy，但这不是代码 commit）。

## 注意事项

- GitHub Actions每月有2000分钟免费额度
- Apify有免费credits，初期够用
- 智谱AI API按调用付费

## 文件结构

```
.
├── .github/
│   └── workflows/
│       └── daily-digest.yml  # 每日自动抓取+摘要+入库
├── scripts/
│   ├── summarize.py          # AI摘要生成
│   ├── send_email.py         # 邮件发送
│   ├── rag_store.py          # RAG 向量存储（ChromaDB + JSON）
│   ├── rag_qa.py             # RAG 智能问答
│   └── rag_trends.py         # RAG 趋势分析
├── app/
│   ├── main.py               # Web服务 + RAG API
│   └── static/
│       └── index.html         # 管理界面（问答/趋势/管理）
├── data/
│   └── tweets_store.json      # 推文数据存储
├── config/
│   ├── users.json             # AI builder列表
│   └── settings.json          # 配置
├── templates/
│   └── email.html             # 邮件模板
├── render.yaml                # Render 部署配置
├── .env.example               # 环境变量模板
└── requirements.txt
```

## 许可证

MIT
