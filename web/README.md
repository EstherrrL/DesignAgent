# 多Agent代码生成系统前端

本前端为多Agent代码生成系统的 Web UI，基于 React + Vite 构建。

## 快速开始

1. 安装依赖：

```bash
cd web
npm install
```

2. 启动开发服务器：

```bash
npm run dev
```

3. 访问 http://localhost:5173

> 默认假设后端 API 运行在 http://localhost:8000，并有 `/api/run` POST 接口。

## 目录结构

- `src/`：前端源码
  - `App.jsx`：主界面
  - `main.jsx`：入口文件
- `index.html`：HTML 模板
- `vite.config.js`：Vite 配置，含 API 代理

## 功能说明

- 输入需求描述，点击提交，前端会向 `/api/run` 发送 POST 请求，展示后端返回的结果。
- 需配合后端 API 使用。

## 依赖
- React 18
- Vite 4+

---

如需自定义 API 地址，请修改 `vite.config.js` 的 `proxy` 配置。
