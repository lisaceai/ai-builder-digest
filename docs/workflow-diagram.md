# AI Builder Daily Digest - 工作流程图

## 主工作流（每日自动执行）

```mermaid
graph LR
    subgraph 触发["🔔 触发"]
        A1[定时任务<br/>UTC 1:20 每日]
        A2[手动触发<br/>workflow_dispatch]
    end

    subgraph 数据采集["📥 数据采集"]
        B1[加载 config/users.json<br/>AI Builder 列表]
        B2[计算昨日时间范围]
        B3[构建 Apify 请求<br/>Twitter Scraper]
        B4[轮询等待结果<br/>每10s / 最长600s]
        B5[下载 raw_tweets.json]
    end

    subgraph AI摘要["🤖 AI 摘要"]
        C1[解析原始推文<br/>处理转推/引用/线程]
        C2[调用智谱 GLM-4.7<br/>逐条生成摘要]
        C3[输出 summarized_tweets.json]
    end

    subgraph RAG入库["💾 RAG 入库"]
        D1[生成唯一 ID<br/>合并摘要+原文]
        D2[更新本地 JSON 缓存<br/>data/tweets_store.json]
        D3[生成 Embedding<br/>智谱 embedding-3]
        D4[写入 Pinecone<br/>向量数据库]
    end

    subgraph 通知归档["📬 通知 & 归档"]
        E1[生成 HTML 邮件<br/>按作者分组]
        E2[SMTP 发送邮件<br/>Gmail TLS]
        E3[上传 GitHub Artifacts<br/>保留 7 天]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2 --> B3 --> B4 --> B5
    B5 --> C1 --> C2 --> C3
    C3 --> D1 --> D2
    D2 --> D3 --> D4
    C3 --> E1 --> E2
    C3 --> E3

    style 触发 fill:#e8f4f8,stroke:#2196F3
    style 数据采集 fill:#fff3e0,stroke:#FF9800
    style AI摘要 fill:#f3e5f5,stroke:#9C27B0
    style RAG入库 fill:#e8f5e9,stroke:#4CAF50
    style 通知归档 fill:#fce4ec,stroke:#E91E63
```

## Web 应用服务流程

```mermaid
graph LR
    subgraph 用户端["👤 用户端"]
        U1[Web 浏览器]
    end

    subgraph FastAPI["⚡ FastAPI 服务"]
        F1[GET /api/health<br/>健康检查]
        F2[GET/POST /api/users<br/>Builder 管理]
        F3[POST /api/rag/ask<br/>RAG 问答]
        F4[GET /api/rag/trends<br/>趋势分析]
        F5[POST /api/rag/builder<br/>Builder 分析]
    end

    subgraph 检索层["🔍 检索层"]
        S1[Pinecone 向量搜索<br/>语义匹配]
        S2[本地 JSON 关键词搜索<br/>正则匹配]
        S3{向量搜索<br/>可用?}
    end

    subgraph LLM["🧠 LLM 生成"]
        L1[组装上下文<br/>检索结果 + 提示词]
        L2[调用智谱 GLM-4.7<br/>严格 RAG 约束]
        L3[返回答案 + 来源]
    end

    U1 --> F1
    U1 --> F2
    U1 --> F3
    U1 --> F4
    U1 --> F5

    F3 --> S3
    F4 --> S3
    F5 --> S3
    S3 -->|是| S1
    S3 -->|否| S2
    S1 --> L1
    S2 --> L1
    L1 --> L2 --> L3 --> U1

    style 用户端 fill:#e3f2fd,stroke:#1976D2
    style FastAPI fill:#fff8e1,stroke:#FBC02D
    style 检索层 fill:#e8f5e9,stroke:#388E3C
    style LLM fill:#f3e5f5,stroke:#7B1FA2
```

## 数据流全景

```mermaid
graph LR
    X[("𝕏 Twitter")] -->|Apify 爬取| RAW[raw_tweets.json]
    RAW -->|智谱 GLM-4.7| SUM[summarized_tweets.json]
    SUM --> JSON[(本地 JSON<br/>tweets_store.json)]
    SUM -->|智谱 Embedding| PC[(Pinecone<br/>向量数据库)]
    SUM --> EMAIL[📧 邮件通知]
    SUM --> ARTIFACT[📦 GitHub Artifacts]

    JSON -->|关键词搜索| QA[RAG 问答 & 分析]
    PC -->|语义搜索| QA
    QA -->|智谱 GLM-4.7| ANSWER[💡 智能回答]

    CFG[config/users.json<br/>Builder 列表] -->|配置输入| X

    style X fill:#1DA1F2,stroke:#0d8bd9,color:#fff
    style RAW fill:#fff3e0,stroke:#FF9800
    style SUM fill:#f3e5f5,stroke:#9C27B0
    style JSON fill:#e8f5e9,stroke:#4CAF50
    style PC fill:#e8f5e9,stroke:#4CAF50
    style EMAIL fill:#fce4ec,stroke:#E91E63
    style QA fill:#fff8e1,stroke:#FBC02D
    style ANSWER fill:#e3f2fd,stroke:#1976D2
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 编排调度 | GitHub Actions (Cron + Manual) |
| 数据采集 | Apify Twitter Scraper |
| AI 模型 | 智谱 GLM-4.7 + embedding-3 |
| 向量数据库 | Pinecone |
| Web 框架 | FastAPI + Uvicorn |
| 部署平台 | Render.com |
| 邮件通知 | SMTP (Gmail) |
