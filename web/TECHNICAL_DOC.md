# 多Agent代码生成系统技术文档

## 项目结构

- `main.py`：后端入口，基于 LangGraph 构建多Agent编排。
- `agents/`：各类智能体（Designer、Coder、Reviewer等）实现。
- `tools/`：代码生成、审查、修复、测试等工具函数。
- `graph/`：LangGraph 状态流转与节点定义。
- `llm/`：大模型 API 封装。
- `models/`：数据结构与 schema。
- `output/`：生成的代码输出。
- `web/`：前端 React + Vite 实现的 Web UI。

## 前端说明

- 技术栈：React 18 + Vite 4
- 主要文件：
  - `web/src/App.jsx`：主界面，输入需求描述，提交后调用 `/api/run`。
  - `web/vite.config.js`：开发代理，前端 `/api` 自动转发到后端（默认 8000 端口）。
- 启动方式：
  1. `cd web && npm install`
  2. `npm run dev`
  3. 浏览器访问 http://localhost:5173 或自动分配端口

## 后端说明

- 主要依赖：Python 3.10+、langgraph、rich
- 入口：`main.py`，支持命令行和（可扩展）API。
- 典型流程：
  1. 用户输入需求
  2. Designer 拆解需求并生成设计文档
  3. Coder 生成代码
  4. Reviewer 审查与评分
  5. 如有需要，循环修复
- 状态管理：`graph/state.py` 定义 PipelineState，所有节点共享。
- 节点定义：`graph/nodes.py`，每个 Agent/路由为一个纯函数节点。
- 流程编排：`graph/pipeline.py`，LangGraph StateGraph 构建完整流程。

## API 设计建议

- 推荐实现 `/api/run` POST 接口，接收需求描述，返回 pipeline 结果。
- 可用 FastAPI、Flask 等快速实现。

## 部署建议

- 前后端分离，前端静态资源可用 nginx/Netlify/Vercel 部署。
- 后端建议使用 gunicorn/uvicorn 部署 API。
- 环境变量通过 `.env` 管理，敏感信息不入库。

## 参考命令

```bash
# 启动前端
cd web && npm install && npm run dev

# 启动后端（假设实现了 API）
python main.py
```

---

如需扩展 Agent、工具或前端功能，建议遵循模块化、解耦、可测试的设计原则。
