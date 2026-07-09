# Design-Code Multi-Agent System

> 用多个 AI Agent 模拟真实软件团队的协作开发流程：**架构师设计 → 工程师编码 → 审查员复核 → 自动测试**

---

## ✨ 核心理念

传统 AI 代码生成是「一次性输出」，质量难以保证。  
本项目引入 **Designer Agent** 作为架构师角色，先输出设计文档，再由 Coder 严格按设计实现，Reviewer 也以设计文档为基准进行审查——**设计文档是整个系统的核心枢纽**。

```
一句需求  →  高质量代码
```

---

## 🏗 系统架构

```
自然语言需求
      │
      ▼
┌──────────────────┐
│  Designer Agent  │  ① 拆解需求 → 子任务列表
│   （核心角色）    │  ② 为每个子任务生成设计文档
│                  │     架构思路 / 组件清单 / 实现步骤 / 注意事项
└────────┬─────────┘
         │  对每个子任务循环：
         ▼
┌──────────────────┐  工具: generate_code（首次）
│   Coder Agent    │◄─────────────────────────────┐
│                  │  工具: apply_fix（修复时）      │ 最多
└────────┬─────────┘                               │ 3 次
         │                                         │
         ▼                                         │
┌──────────────────┐  工具: review_code            │
│  Reviewer Agent  │  以设计文档为基准审查          │
│                  │  得分 < 7.0 → 反馈给 Coder ───┘
└────────┬─────────┘
         │ 通过（≥ 7.0）→ 进入下一子任务
         ▼
┌──────────────────┐
│  Assembler       │  合并所有子任务代码
└────────┬─────────┘
         ▼
┌──────────────────┐  工具: run_tests
│  Tester          │  Python: 实际执行验证
└────────┬─────────┘  JS/TS: 语法检查 | 其他: 静态分析
         ▼
   output/task_<id>.<ext>
```

---

## 🤖 Agent 角色说明

### 🎨 Designer Agent（核心）
整个系统的**大脑**，承担两个关键职责：

1. **需求拆解** — 将自然语言需求分解为 2-6 个可独立实现的子任务
2. **设计文档生成** — 为**每个子任务**单独产出结构化设计文档，包含：
   - 整体架构思路与设计模式
   - 需要实现的组件 / 函数签名
   - 逐步实现计划（Step-by-step）
   - 边界情况与质量注意点

设计文档会同时传递给 Coder（作为实现规范）和 Reviewer（作为审查基准），确保三者在同一标准下协作。

### 💻 Coder Agent
- **首次生成**：调用 `generate_code`，严格按照 Designer 的设计文档实现代码
- **迭代修复**：调用 `apply_fix`，根据 Reviewer 的具体问题进行针对性修复，同时保持对设计文档的忠实度

### 🔍 Reviewer Agent
- 调用 `review_code`，**以设计文档为基准**审查代码
- 评分维度：设计符合度 / 完整性 / 正确性 / 健壮性 / 代码质量
- 输出 0-10 分，附详细问题列表和改进建议
- 得分 ≥ 7.0 视为通过

### 🎛 Orchestrator
- 驱动完整 Pipeline，维护全局状态
- 每个子任务最多允许 `MAX_TASK_ATTEMPTS`（默认 3）次 Coder-Reviewer 循环
- 3 次仍未通过 → 记录问题，强制推进下一子任务
- 通过 Rich 提供实时彩色进度展示

---

## 🛠 四个核心工具

| 工具 | 调用时机 | 功能 |
|------|---------|------|
| `generate_code` | Coder 首次生成 | 将设计文档转化为完整代码 |
| `review_code` | Reviewer 审查 | 基于设计文档评分，输出问题列表 |
| `apply_fix` | Coder 迭代修复 | 针对审查问题修复，不偏离设计文档 |
| `run_tests` | 最终验证 | Python 沙盒执行 / JS 语法检查 / 静态分析 |

---

## 📁 目录结构

```
DesignAgent/
├── main.py                  # 入口（交互 / 命令行两种模式）
├── config.py                # 全局配置（读取 .env）
├── .env.example             # 配置模板
├── requirements.txt
│
├── llm/
│   └── client.py            # LLMClient 单例（ARK / OpenAI 兼容接口）
│
├── models/
│   └── schemas.py           # 数据结构：DesignDoc / CodeResult / ReviewResult …
│
├── tools/
│   ├── generate_code.py     # 工具①：按设计文档生成代码
│   ├── review_code.py       # 工具②：基于设计文档审查代码
│   ├── apply_fix.py         # 工具③：针对性修复（保持设计一致）
│   └── run_tests.py         # 工具④：执行验证代码
│
├── agents/
│   ├── base_agent.py        # 抽象基类
│   ├── designer.py          # ⭐ Designer Agent（核心）
│   ├── coder.py             # Coder Agent
│   ├── reviewer.py          # Reviewer Agent
│   └── orchestrator.py      # Orchestrator（调度器）
│
├── utils/
│   └── logger.py            # Rich 彩色日志
│
└── output/                  # 生成的代码文件（自动创建）
```

---

## 🚀 快速开始

### 1. 克隆 & 安装依赖

```bash
git clone https://github.com/EstherrrL/DesignAgent.git
cd DesignAgent
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 ARK API 配置：

```ini
ARK_API_KEY=your_api_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL_EP=your_endpoint_id      # 格式：ep-xxxxxxxxxxxxxxxx-xxxxx
MAX_TASK_ATTEMPTS=3                # 每个子任务最多重试次数
MIN_QUALITY_SCORE=7.0              # 审查通过分数线
```

### 3. 运行

```bash
# 交互模式（命令行提示输入需求）
python main.py

# 直接传入需求
python main.py "用 Python 实现带 TTL 的线程安全 LRU 缓存"
python main.py "Create a Go HTTP server with rate limiting middleware"
```

---

## 📊 运行示例

```
需求：用 Python 实现二分查找，要求类型注解和完善的错误处理

Step 1 Designer  → 拆解为 3 个子任务
                   ├─ st_1: 定义函数和参数类型
                   ├─ st_2: 实现二分查找逻辑  
                   └─ st_3: 添加错误处理

Step 2 Designer  → 为 [定义函数和参数类型] 生成设计文档
Step 3 Coder     → 按设计文档生成代码（第 1/3 次）
Step 4 Reviewer  → 得分 9.0/10 ✅ 通过 → 进入下一子任务

Step 2 Designer  → 为 [实现二分查找逻辑] 生成设计文档
Step 3 Coder     → 按设计文档生成代码（第 1/3 次）
Step 4 Reviewer  → 得分 9.0/10 ✅ 通过 → 进入下一子任务

Step 2 Designer  → 为 [添加错误处理] 生成设计文档
Step 3 Coder     → 按设计文档生成代码（第 1/3 次）
Step 4 Reviewer  → 得分 9.0/10 ✅ 通过

Step 5 Assembler → 合并所有子任务代码
Step 6 Tester    → ✅ 2/2 测试通过（0.032s）

💾 代码已保存至 output/task_d0f71f10.py
```

---

## 📤 输出

- 最终代码保存在 `output/task_<task_id>.<ext>`
- 文件头部包含任务 ID、子任务通过率、需求描述
- 多子任务代码按段落合并，每段带清晰注释头
- 控制台实时展示每个 Agent 的执行详情（Rich 渲染）

---

## 🔧 支持的语言

Python（沙盒执行验证）· JavaScript / TypeScript（语法检查）· Java · Go · Rust · C++ · Ruby · 及其他（静态分析）


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
