# 后端 Demo

本后端示例使用 FastAPI 提供一个最小的 `/api/run` 接口，演示如何把前端（`web/`）与现有 LangGraph pipeline 连接。

## 快速启动

1. 创建并激活 Python 虚拟环境（如果尚未）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
pip install fastapi uvicorn
```

2. 启动后端：

```bash
cd backend
uvicorn demo:app --reload --port 8000
```

3. 启动前端（另一个终端）：

```bash
cd web
npm run dev
```

4. 在前端页面输入需求并提交，或直接用 curl 调用：

```bash
curl -X POST http://localhost:8000/api/run -H "Content-Type: application/json" -d '{"input":"生成一个加法函数的 Python 文件"}'
```
