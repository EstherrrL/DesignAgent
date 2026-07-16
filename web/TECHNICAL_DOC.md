
# 多Agent代码生成系统前端技术文档（详细版）

---

## 1. 项目结构与职责分层

```
多agent/
├── web/                # 前端 React + Vite
│   ├── src/
│   │   └── App.jsx     # 主界面入口
│   ├── vite.config.js  # Vite 配置，含 API 代理
│   ├── package.json    # 前端依赖与脚本
│   └── TECHNICAL_DOC.md# 本文档
├── backend/            # FastAPI/uvicorn 后端（/api/run）
├── agents/             # 多智能体实现
├── tools/              # 代码生成/修复/测试工具
├── graph/              # LangGraph 流程编排
└── ...
```

---

## 2. 前端架构说明

- **技术栈**：React 18 + Vite 4
- **开发体验**：Vite 热更新，零配置，启动快
- **依赖管理**：npm（见 `package.json`）
- **主要依赖**：
  - `react`, `react-dom`：UI 框架
  - `vite`：前端构建与本地开发服务器
  - `@vitejs/plugin-react`：JSX/TSX 支持

---

## 3. 主要文件与目录

- `src/App.jsx`：主界面，包含：
  - 需求输入框、提交按钮
  - 结果展示区（设计文档、生成文件、审查、测试结果）
  - 文件下载、loading 动画、错误重试等
- `vite.config.js`：配置 `/api` 代理到后端（开发时避免跨域）
- `package.json`：依赖与脚本
- `index.html`：单页应用入口

---

## 4. 启动与开发流程

1. 安装依赖
   ```bash
   cd web
   npm install
   ```
2. 启动开发服务器
   ```bash
   npm run dev
   ```
   - 默认端口 5173，如被占用自动切换（5174/5175...）
   - 终端输出实际访问地址
3. 访问
   - 浏览器打开 http://localhost:5173 或终端提示的端口
   - 若端口冲突（如有其他项目占用），Vite 会自动切换端口

---

## 5. 前后端接口约定

- **接口**：`POST /api/run`
  - 请求体：`{ input: string }`  // 用户需求描述
  - 响应体：
    ```json
    {
      "ok": true,
      "result": {
        "design_doc": "...",
        "files": { "filename.py": "...code..." },
        "review": { "score": 9.0, "comments": "..." },
        "test_result": { "passed": true, "output": "...", "errors": [] }
      }
    }
    ```
  - 失败时：`{ ok: false, error: "..." }`
- **前端代理**：开发环境下 `/api` 自动转发到 `localhost:8000`（见 vite.config.js）

---

## 6. 关键组件说明

- `App.jsx`：
  - `input`：需求输入框，回车或点击提交
  - `handleSubmit`：调用 `/api/run`，处理 loading/error 状态
  - `FileList`：展示生成的文件，支持下载
  - `LoadingPanel`：加载动画与耗时统计
  - 结果区：分块展示设计文档、代码、审查、测试结果
  - 错误处理：网络异常/LLM超时/后端报错均有提示与重试

---

## 7. 常见问题与排查

- **端口冲突**：
  - 5173/5174/5175 被其他项目占用时，Vite 会自动切换端口
  - 终端输出实际端口，需用对应端口访问
- **接口 404/跨域**：
  - 确认后端已启动（默认 8000）
  - 前端开发环境下 `/api` 由 Vite 代理，无需手动配置 CORS
- **依赖问题**：
  - `npm install` 后如有缺失/冲突，尝试 `rm -rf node_modules && npm install`
- **前端白屏/报错**：
  - 检查控制台报错，确认 `/api/run` 能正常返回
  - 检查 `App.jsx` 逻辑是否有异常

---

## 8. 生产部署建议

- 前端构建：
  ```bash
  npm run build
  # 产物在 web/dist，可用 nginx/Netlify/Vercel 部署
  ```
- 后端部署：
  - 推荐 gunicorn/uvicorn，生产环境关闭 reload
  - 环境变量用 `.env` 管理，敏感信息不入库
- 前后端分离，接口通过 HTTPS 代理

---

## 9. 代码风格与扩展建议

- 组件拆分：建议将大组件（如文件列表、loading、错误提示）独立为子组件
- 状态管理：简单场景用 useState/useEffect，复杂可引入 Redux/Zustand
- 样式：可用 CSS Modules、Tailwind、AntD 等
- 国际化：如需多语言支持可引入 i18next
- 代码注释与类型：建议补充 JSDoc/TypeScript 类型注释

---

## 10. 参考命令

```bash
# 启动前端
cd web && npm install && npm run dev

# 构建前端
npm run build

# 启动后端（需先配置好 LLM/环境变量）
cd backend && python demo.py
```

---

如需扩展 Agent、工具或前端功能，建议遵循模块化、解耦、可测试的设计原则。
