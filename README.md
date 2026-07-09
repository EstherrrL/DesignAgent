# Multi-Agent Code Generation System

一个基于多 Agent 协作的代码生成系统，通过 **Planner → Coder → Reviewer** 迭代循环生成高质量代码。

---

## 系统架构

```
自然语言需求
      │
      ▼
┌─────────────┐
│   Planner   │  拆解任务 → PlanResult（语言 + 子任务 + 测试用例）
└──────┬──────┘
       │
       ▼
┌─────────────┐  工具: generate_code（迭代 0）
│    Coder    │◄──────────────────────────────────────┐
└──────┬──────┘  工具: apply_fix   （迭代 1+）         │
       │                                               │
       ▼                                               │
┌─────────────┐  工具: review_code                     │
│  Reviewer   │  得分 < 阈值(7.0) 且迭代未超限 ──────────┘
└──────┬──────┘
       │ 得分 ≥ 7.0 或达到 MAX_ITERATIONS
       ▼
┌─────────────┐  工具: run_tests
│  Tester     │  Python: 实际执行；JS: 语法校验；其他: 静态分析
└──────┬──────┘
       │
       ▼
  output/task_<id>.<ext>
```

---

## 目录结构

```
多agent/
├── main.py                  # 入口
├── config.py                # 全局配置（读取 .env）
├── .env                     # 环境变量
├── requirements.txt
│
├── llm/
│   └── client.py            # LLMClient 单例（ARK / OpenAI 兼容）
│
├── models/
│   └── schemas.py           # 所有数据结构（PlanResult / CodeResult / …）
│
├── tools/
│   ├── generate_code.py     # 工具：调用 LLM 生成代码
│   ├── review_code.py       # 工具：调用 LLM 审查代码
│   ├── apply_fix.py         # 工具：调用 LLM 针对性修复
│   └── run_tests.py         # 工具：执行/验证代码
│
├── agents/
│   ├── base_agent.py        # 抽象基类
│   ├── planner.py           # Planner Agent
│   ├── coder.py             # Coder Agent
│   ├── reviewer.py          # Reviewer Agent
│   └── orchestrator.py      # Orchestrator（调度所有 Agent）
│
├── utils/
│   └── logger.py            # Rich 彩色日志
│
└── output/                  # 生成的代码文件（自动创建）
```

---

## 快速开始

### 1. 安装依赖

```bash
cd /path/to/多agent
pip install -r requirements.txt
```

### 2. 配置环境变量

`.env` 文件已预设 ARK API 配置，可按需修改：

```ini
ARK_API_KEY=your_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL_EP=your_endpoint
MAX_ITERATIONS=5
MIN_QUALITY_SCORE=7.0
```

### 3. 运行

```bash
# 交互模式
python main.py

# 命令行直接传入需求
python main.py "用 Python 实现带 TTL 的线程安全 LRU 缓存"
python main.py "Create a Go HTTP server with rate limiting middleware"
```

---

## 核心组件说明

| 组件 | 角色 | 使用工具 |
|------|------|---------|
| **PlannerAgent** | 需求分析 → 任务拆解 | LLM 直接调用 |
| **CoderAgent** | 代码生成 / 修复 | `generate_code`（iter 0）/ `apply_fix`（iter 1+）|
| **ReviewerAgent** | 代码质量审查（0-10 分）| `review_code` |
| **Orchestrator** | 调度 + 状态管理 | `run_tests`，驱动上述所有 Agent |

### 迭代机制

1. 每轮：Coder 生成/修复代码 → Reviewer 打分
2. 得分 ≥ `MIN_QUALITY_SCORE`（默认 7.0）→ 退出循环
3. 未通过且未超 `MAX_ITERATIONS`（默认 5）→ 继续迭代
4. 退出循环后执行 `run_tests` 验证

---

## 输出

- 生成的代码保存在 `output/task_<task_id>.<ext>`
- 文件头部包含任务 ID、质量得分、需求描述
- 控制台实时展示每个 Agent 的执行过程（Rich 渲染）
