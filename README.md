<h1 align="center">Paper-Agent: AI 学术论文调研报告生成系统</h1>

<p align="center">
  <a href="https://github.com/Tswoen/paper-agent">GitHub</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#项目结构">项目结构</a>
</p>

## 简介

**Paper-Agent** 是一个面向科研人员的自动化调研报告生成系统。输入一个研究话题，系统自动完成：

1. **搜索** — 从 Semantic Scholar 检索相关论文
2. **阅读** — 并行提取论文的核心问题、方法、数据集、结果等结构化信息
3. **分析** — 三阶段分析（聚类 → 深度分析 → 全局分析）
4. **写作** — 自动生成大纲，逐章撰写综述内容（含检索增强 + 自动审阅）
5. **报告** — 输出完整 Markdown 报告，可复制/下载

## 项目预览

| 首页 | 进度 | 报告 |
|------|------|------|
| `├─ 左侧输入面板 ├─ 右侧报告展示区 ┤` | 实时步骤进度 + 流式生成内容 | Markdown 渲染 + 复制/下载 |

## 核心特性

- 🔍 **Semantic Scholar 检索** — 智能生成英文查询词，从 Semantic Scholar 搜索论文
- 📖 **并行论文阅读** — LLM 提取论文结构化信息（核心问题、方法、数据集、局限性等）
- 🧠 **三阶段分析** — 聚类分析 → 深度分析 → 全局分析，识别研究趋势
- ✍️ **多 Agent 协作写作** — 检索增强 + 自动审阅 + 迭代修改
- 📝 **Markdown 报告输出** — 结构化综述，保存到 `output/` 目录，支持下载
- 🔄 **SSE 实时推送** — 前端实时显示进度和流式内容
- 📚 **知识库增强** — 上传 PDF/TXT/MD 等文件，写作时自动检索相关知识
- 🎛️ **Web 管理界面** — Vue 3 前端，知识库 CRUD、历史报告管理

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | FastAPI + Uvicorn |
| **LLM 编排** | LangChain LCEL（纯 async/await 编排） |
| **LLM 服务** | SiliconFlow API（Qwen3-8B + Qwen3-Embedding-8B） |
| **论文检索** | Semantic Scholar API + arXiv 回退 |
| **向量数据库** | ChromaDB |
| **前端** | Vue 3 + Vite + marked + DOMPurify |
| **实时通信** | SSE（Server-Sent Events） |

## 项目结构

```
Paper-Agent/
├── main.py                  # FastAPI 入口，启动服务
├── .env                     # 环境变量（API Key、模型配置）
├── README.md                # 项目说明
├── paper_agent/             # 核心包
│   ├── config.py            # 配置管理（从 .env 读取）
│   ├── models.py            # Pydantic 数据模型
│   ├── orchestrator.py      # 流程编排（search → read → analyze → write → report）
│   ├── prompts.py           # LLM Prompt 模板
│   ├── agents/              # Agent 模块
│   │   ├── retrieval_agent.py   # 检索增强 Agent
│   │   └── review_agent.py      # 审阅 Agent
│   ├── api/                 # REST API
│   │   └── knowledge_api.py     # 知识库 CRUD + 文件上传 API
│   ├── chains/              # LangChain 处理链
│   │   ├── search_chain.py      # 论文检索链
│   │   ├── reading_chain.py     # 论文阅读链
│   │   ├── analysis_chain.py    # 三阶段分析链
│   │   ├── writing_chain.py     # 大纲+写作链（含 Agent 协作）
│   │   └── report_chain.py      # 报告组装链
│   ├── knowledge/           # 知识库模块
│   │   ├── kb_manager.py        # ChromaDB 知识库管理
│   │   └── kb_embedder.py       # 文档嵌入处理
│   └── services/            # 外部服务
│       ├── semantic_scholar_client.py  # Semantic Scholar API 客户端
│       ├── arxiv_client.py             # arXiv 回退客户端
│       └── vector_store.py             # ChromaDB 向量存储
├── web/                     # 前端
│   ├── src/
│   │   ├── App.vue              # 布局外壳（顶部导航）
│   │   ├── AppRoot.vue          # 根组件
│   │   ├── router/index.js      # 路由
│   │   ├── api/knowledge.js     # 知识库 API 封装
│   │   ├── views/
│   │   │   ├── HomePage.vue     # 首页（输入+报告）
│   │   │   ├── History.vue      # 历史报告
│   │   │   └── KnowledgeBase.vue # 知识库管理
│   │   └── components/          # 通用组件
│   ├── vite.config.js
│   └── index.html
├── data/                     # ChromaDB 运行时数据
└── output/                   # 生成的报告
```

## 工作流程

```
用户输入话题
  → LLM 生成英文查询词
  → Semantic Scholar 检索论文
  → 并行提取论文结构化信息 → 存入 ChromaDB
  → 三阶段分析（聚类 → 深度 → 全局）
  → 生成写作大纲
  → 逐章写作（检索增强 + 自动审阅 + 迭代修改）
  → 拼接 Markdown 报告 → 保存 output/
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+（前端）

### 1. 安装依赖

```bash
git clone https://github.com/Tswoen/paper-agent.git
cd paper-agent

# Python 依赖
pip install fastapi uvicorn langchain langchain-openai chromadb \
    httpx pydantic python-dotenv openai sse-starlette

# 前端依赖
cd web && npm install && cd ..
```

### 2. 配置 .env

```env
# LLM 配置
SILICONFLOW_API_KEY=sk-your-key-here
LLM_MODEL=Qwen/Qwen3-8B
LLM_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B

# Semantic Scholar API（可选，有 key 可提高速率限制）
SEMANTIC_SCHOLAR_API_KEY=
SEMANTIC_SCHOLAR_BASE_URL=https://api.semanticscholar.org/graph/v1
SEMANTIC_SCHOLAR_TIMEOUT=30
```

### 3. 启动服务

```bash
# 终端 1：启动后端
python main.py
# 服务运行在 http://localhost:8000

# 终端 2：启动前端
cd web && npm run dev
# 前端运行在 http://localhost:5173
```

打开浏览器访问 `http://localhost:5173`，输入话题即可开始调研。

## 知识库使用

1. 访问前端「知识库」页面，上传 PDF/TXT/MD/DOCX 等文件
2. 回到首页，在左侧面板选择知识库
3. 提交调研时，写作会自动检索知识库中的相关内容

## 常见问题

**Q: 生成速度慢？**
A: 系统采用串行写作避免 API 限流，14 个章节约需 3-8 分钟。可通过调整 `.env` 中的 `LLM_MODEL` 使用更快模型。

**Q: 搜索不到论文？**
A: Semantic Scholar 免费 API 限制 1 req/s，系统已内置速率限制。确保网络能访问 `api.semanticscholar.org`。

## 许可证

MIT License

## Star 历史

[![Star History Chart](https://api.star-history.com/image?repos=Tswoen/Paper-Agent&type=date&legend=top-left)](https://www.star-history.com/?repos=Tswoen%2FPaper-Agent&type=date&legend=top-left)
