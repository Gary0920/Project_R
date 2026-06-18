# Project_R Windows 新电脑依赖安装与运行说明

本文用于在一台全新的 Windows 电脑上从源码运行 Project_R。当前项目由 FastAPI 后端和 Electron + React + Vite 前端组成。

## 1. 推荐系统环境

- Windows 10 / Windows 11
- PowerShell 5+ 或 Windows Terminal
- Git
- Python 3.11.x
- Node.js 24.x 或当前 LTS 版本
- Bun 1.x

> 备注：根目录不需要安装 Node 依赖。前端依赖只安装在 `frontend/`，后端 Python 依赖只安装在 `backend/venv/`。

## 2. 安装基础工具

以管理员身份打开 PowerShell，执行：

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
winget install --id OpenJS.NodeJS -e
powershell -ExecutionPolicy Bypass -c "irm bun.sh/install.ps1 | iex"
```

安装完成后，重新打开 PowerShell，检查版本：

```powershell
git --version
py -3.11 --version
node --version
npm --version
bun --version
```

## 3. 获取项目代码

如果 GitHub 仓库已确认是最新版本，使用：

```powershell
git clone https://github.com/Gary0920/Project_R.git
cd Project_R
```

如果使用 Gary 提供的源码运行包，解压后进入目录：

```powershell
cd Project_R-runtime-windows
```

## 4. 后端依赖安装

```powershell
cd backend
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

首次运行前复制环境变量示例：

```powershell
Copy-Item .env.example .env
notepad .env
```

按需填写真实 LLM API Key、Provider 配置等。`.env` 含敏感信息，不应提交到 GitHub，也不会放入源码运行包。

联网搜索默认使用 Tavily Search API。若要启用前端“联网搜索”开关，需要在 `.env` 中确认：

```env
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY_1=tvly-你的第一个key
TAVILY_API_KEY_2=tvly-你的第二个key
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=5
```

也可以使用逗号写法：

```env
TAVILY_API_KEYS=tvly-你的第一个key,tvly-你的第二个key
```

真实 Key 只允许写入 `backend/.env`，不得提交到 GitHub。后端会轮询使用多个 Tavily Key；当某个 Key 返回认证、额度、限流、网络或 5xx 类错误时，会在本次请求中尝试下一个 Key。

## 5. 前端依赖安装

打开新的 PowerShell，进入项目目录后执行：

```powershell
cd frontend
bun install
```

## 6. 本地验证

后端测试：

```powershell
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests
```

前端构建：

```powershell
cd frontend
bun run build
```

## 7. 启动开发环境

启动后端：

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd frontend
bun run dev
```

开发期后端默认地址为：

```text
http://localhost:8000
```

管理员账号：

```text
sysadmin / Admin123
```

## 8. 大体积依赖与缓存说明

以下内容不建议放入 GitHub 或源码运行包：

- `backend/venv/`：Python 虚拟环境，可通过 `requirements.txt` 重新安装。
- `frontend/node_modules/`：前端依赖，可通过 `bun install` 重新安装。
- `frontend/dist/`：前端构建产物，可通过 `bun run build` 重新生成。
- `backend/app.db`、根目录 `app.db`：本机 SQLite 数据库。
- `backend/workspace_data/`：本机工作区上传资料。
- `backend/generated_files/`：运行时生成的 Word/Excel 等文件。
- `backend/vector_store/`：本机向量库缓存。
- `backend/models_cache/`：本机 embedding 模型缓存，体积很大。
- `backend/logs/`：运行日志。
- `.env`：真实密钥和本机配置。

如果新电脑不能联网，`backend/models_cache/` 需要另行离线复制；如果可以联网，首次使用本地 embedding/RAG 能力时可重新下载模型缓存。

## 9. 当前依赖声明文件

- 后端：`backend/requirements.txt`
- 前端：`frontend/package.json`
- 前端锁文件：`frontend/bun.lock`

新增依赖时必须写入对应依赖声明文件，不能只安装在本机环境中。
