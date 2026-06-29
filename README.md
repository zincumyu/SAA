# AI 学习平台 - 极简原型

Vue + Python 全栈，AI 学习网站原型。

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | **FastAPI** (Python) | 单文件路由 + 数据库操作 |
| 数据库 | **SQLite** | Python 自带，数据文件在 `backend/data/saa.db` |
| 图片存储 | **文件系统** | 图片保存在 `backend/data/images/` |
| 前端 | **Vue 3** (CDN) | 单 HTML 文件，无需 Node.js / 构建工具 |
| 通信 | REST API + Bearer Token | 登录后所有请求带 Authorization header |

## 项目结构

```
SAA_0/
├── backend/
│   ├── __init__.py         # Python 包标记
│   ├── main.py             # 🐍 FastAPI 后端（路由 + AI 接口）
│   ├── database.py          # 🗄️ SQLite 数据库操作（用户 + 错题本 CRUD）
│   ├── requirements.txt    # Python 依赖
│   └── data/               # 自动生成的数据目录
│       ├── saa.db           # SQLite 数据库文件
│       └── images/          # 错题本图片
├── frontend/
│   └── index.html           # 🎨 Vue 3 前端（全部页面）
├── run.py                   # 🚀 一键启动
└── README.md
```

## 快速开始

```bash
pip install -r backend/requirements.txt
python run.py
# 访问 http://localhost:8000
```

## API 文档

启动后访问: **http://localhost:8000/docs**（Swagger 自动生成）

### 用户系统

| 接口 | 方法 | 说明 | 需登录 |
|---|---|---|---|
| `/api/register` | POST | 注册 | ❌ |
| `/api/login` | POST | 登录，返回 token | ❌ |

### AI

| 接口 | 方法 | 说明 | 需登录 |
|---|---|---|---|
| `/api/chat` | POST | AI 对话（已接入 DeepSeek） | ❌ |
| `/api/image-recognize` | POST | 图片识别（骨架） | ❌ |

### 错题本

| 接口 | 方法 | 说明 | 需登录 |
|---|---|---|---|
| `/api/errorbook` | GET | 获取当前用户的错题列表 | ✅ |
| `/api/errorbook` | POST | 添加错题（可选图片 base64） | ✅ |
| `/api/errorbook/{id}` | PUT | 修改错题 | ✅ |
| `/api/errorbook/{id}` | DELETE | 删除错题（同时删除关联图片） | ✅ |
| `/api/errorbook/image/{filename}` | GET | 查看错题配图 | ❌ |

## 数据如何管理？

### 查看数据

```
📁 backend/data/
   ├── saa.db        ← SQLite 数据库，包含所有用户和错题本数据
   └── images/       ← 错题本上传的图片
```

**查看/编辑数据库**（任选一种）：

1. **命令行**：`sqlite3 backend/data/saa.db` → `.tables` → `SELECT * FROM users;`
2. **GUI 工具**：下载 [DB Browser for SQLite](https://sqlitebrowser.org/)（免费），打开 `saa.db` 即可可视化浏览和编辑
3. **Python**：
```python
import sqlite3
conn = sqlite3.connect('backend/data/saa.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM errorbook").fetchall()
for r in rows: print(dict(r))
```

### 数据隔离机制

- 每个用户注册后获得唯一 `token`
- 前端所有请求携带 `Authorization: Bearer <token>`
- 后端 `get_current_user()` 根据 token 识别用户
- **所有错题本查询都带 `WHERE user_id=?`，确保用户只能看到自己的数据**

### 备份数据

直接复制 `backend/data/` 整个目录即可备份所有数据。

## 前端页面

| 路由 | 页面 | 说明 | 需登录 |
|---|---|---|---|
| `#/` | 欢迎页 | 项目介绍 + 入口 | ❌ |
| `#/login` | 登录/注册 | 支持切换登录和注册 | ❌ |
| `#/chat` | AI 对话 | 聊天界面，已接入 DeepSeek | ✅ |
| `#/image` | 图片识别 | 上传图片并分析 | ✅ |
| `#/errorbook` | 错题本 | 添加/编辑/删除错题，支持图片和科目标签 | ✅ |
| `#/knowledge` | 知识库 | 占位（待开发） | ✅ |

## 如何扩展

### 添加新功能页面

1. 在 `frontend/index.html` 末尾创建新的 Vue 组件
2. 在 `routes` 中添加路由
3. 在 `MainLayout` 侧边栏添加菜单项
4. 在 `backend/main.py` 中添加 API 路由

### 接入新的 AI 模型

在 `backend/main.py` 的 `/api/chat` 中修改 `model`、`base_url` 等参数即可。

### 前端拆分

当 `index.html` 变大后，可将 JS 和 CSS 拆分：

```
frontend/
├── index.html       # 入口 + 布局
├── js/
│   ├── chat.js      # 聊天组件
│   └── errorbook.js # 错题本组件
└── css/
    └── style.css
```
