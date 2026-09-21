# 万维文 WitWork

> 万维文 AI 写作：汇万千思路，写一纸文章。

本地优先的「人机实时协作写作系统」——AI 长篇写作 + 自有世界观知识库 + 一致性管理，全部在本机运行，离线可用、无云端、不上传任何数据。

- 中文名：**万维文**
- 英文名：**Wit Work Word**，简称 **WitWork**
- 定位：给小说家的本地 AI 写作协作桌面应用

---

## 它能做什么

- **AI 长篇协作**：本地模型（如 Ollama）或任意 OpenAI 兼容服务，流式续写 / 润色 / 扩写 / 世界观问答，密钥本地加密存储。
- **自有知识库**：世界观、人物、势力、情节、地点、词条、素材分区管理；向量 + 关键词双路检索（默认哈希降级，离线即开即用）。
- **一致性管理**：人物卡、伏笔生命周期、异写归一、爽点节奏、跨章搜索替换。
- **多格式导出**：Word / Markdown / EPUB / 设定 MD·JSON / TXT，导出前经排版引擎修正标点、引号、段首缩进。
- **备份与恢复**：一键打包数据库 + 配置 + 上传，恢复前自动再打 `pre-restore` 备份，误操作可逆。
- **功能面板（HUD）**：时钟、今日事项、日程倒计时、歌曲识别（Windows SMTC，含封面 / 旋律可视化 / 音量 / 换曲）、专注时长。
- **默认 AI 协作助手**：「默认万维文」人格，可自由调整或直接用自然语言叠加人格 overlay。

---

## 许可证

本软件采用 **非商业许可证（NC License）**：**可以自用、可以修改、可以免费分发，但不得用于任何商业目的**（销售、SaaS、内嵌于商业产品、收费代写服务等均需事先书面授权）。

详见 [LICENSE](./LICENSE)。商业使用请联系作者签署商业授权协议。

---

## 快速开始（本地优先）

### 方式一：双击即用（推荐）
双击 `start.bat`：
- 首次运行自动建 Python 虚拟环境并安装依赖（需本机有 `python`）；
- 服务起来后自动打开浏览器到 `http://127.0.0.1:8723/`；
- 重复双击只会再开一个浏览器标签，不会拉起第二份服务。

停止服务：关掉 `start.bat` 打开的黑色窗口（或结束 `python -m server.main` 进程）。

### 方式二：手动启动
```bash
# 在仓库根目录
venv\Scripts\python.exe -m server.main        # Windows
# 或（非 Windows）
PYTHONPATH=. venv/bin/python -m server.main
```
服务监听 `127.0.0.1:8723`（仅本机）。

### 接入 AI 模型
默认已种两个 Provider：**本地演示 (mock)**（离线假数据，用于体验界面）和 **本地 Ollama**（指向 `http://127.0.0.1:11434`）。
用真实模型前先装并启动 [Ollama](https://ollama.com) 并拉模型，例如：
```bash
ollama pull qwen2.5:7b
ollama pull qwen3:14b     # 更强
ollama pull deepseek-r1:7b   # 推理型
```
在「AI 助手」里选 Provider、点「测试」即可。

### 从源码构建前端（可选）
仓库中的 `web/` 为已构建产物；如需自行重建：
```bash
cd web-astro
npm install
node_modules/.bin/astro build      # 产物输出到 web-astro/dist
python web-astro/deploy_astro.py   # 部署到 web/（FastAPI 托管）
```
桌面版（Electron）打包见 `desktop/`，需先有 `web/` 与 `venv/`。

---

## 目录结构（源码）

```
server/         FastAPI 后端 + SQLite（单一真源）+ 服务（SMTC、导出、备份…）
web-astro/      前端源码（Astro + Vue + Three.js），构建后由 FastAPI 托管
desktop/        Electron 桌面包装（electron-main / preload / 打包配置）
tools/          开发期脚本（冒烟测试、诊断、桌面快捷方式…）
使用说明.md      完整使用手册（界面、AI 协作、一致性工具、导出、备份、排障）
```

> 注：代码与目录内部仍沿用 `inkrealm` 作为工程标识（环境变量、数据库文件、打包资源路径），以保证构建与历史数据兼容；对外品牌统一为 **万维文 / WitWork**。
