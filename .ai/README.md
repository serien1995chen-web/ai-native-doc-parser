---
 lang: zh-CN
 title: 多 Agent 协作开发全流程 · 导航手册
---

# 多 Agent 协作开发全流程导航

本文档是 **`.ai/`** 目录的总导航，定义四个 Agent 角色之间的协作流程、信息传递机制以及团队分工策略。

---

## 1. 文件结构预览

```
.ai/                     # AI Agent 专用上下文目录（置于项目根目录）
├── README.md            # 总导航（本文档）
└── PROMPTS/
    ├── planning.md      # Plan Agent 规则
    ├── coding.md        # Coding Agent 规则
    ├── review.md        # Review Agent 规则
    └── pr-review.md     # PR Review Agent 规则
```

---

## 2. 角色总览

| 角色 | 窗口 | 核心职责 |
|------|------|----------|
| **开发者（你）** | 主控窗口 | 任务输入、信息中转、最终决策、git push 与合并 |
| **Plan Agent** | 窗口 1 | 出计划，不执行不审查 |
| **Coding Agent** | 窗口 2 | 编码 + 测试 + git 本地提交 |
| **Review Agent** | 窗口 3 | 审查代码，区分实现偏差 / 方案问题 |
| **PR Review Agent** | 窗口 4（PR 阶段） | 审查 PR diff 兼容性，兜底发现遗漏 Bug |

---

## 3. 启动前准备

启动一次多 Agent 协作开发前，需要满足以下前置条件：

- 项目已克隆到本地，当前处于 `main` 分支并已拉取最新代码
- 项目系统设计文档已就绪（由人工拖入对应 Agent 窗口）
- 开发者手里有一份清晰的任务描述（或 Issue / 需求清单）
- 四个 Codex 窗口已打开，各自已读取对应的规则文件：
  - 窗口 1 → `.ai/PROMPTS/planning.md`
  - 窗口 2 → `.ai/PROMPTS/coding.md`
  - 窗口 3 → `.ai/PROMPTS/review.md`
  - 窗口 4 → `.ai/PROMPTS/pr-review.md`

---

## 4. 完整工作流程

### 4.1 流程图

```text
┌─────────────────────────────────────────────────────────────────┐
│                        开发阶段（窗口 1-3）                      │
└─────────────────────────────────────────────────────────────────┘

  [开发者] 准备：任务描述 + 系统设计文档
       │
       ▼
  [Planner Agent]  读取规划.md + 系统设计文档 + 任务
       │  输出：实现方案
       │
  [开发者] 将方案传给 Coding Agent 窗口
       │
       ▼
  [Coding Agent]  读取 coding.md + 方案
       │  编码 → 测试 → git add → git commit
       │  输出：工作完成情况
       │
  [开发者] 通知 Review Agent 开始审查
       │
       ▼
  [Review Agent]  读取 review.md + 方案 + 完成情况
       │  ┌─────────────────────────────────────────────┐
       │  │  审查通过 → [开发者] git push + 发起 PR    │
       │  │                                            │
       │  │  实现偏差 → 结构化报告 → 回 Coding 修复    │
       │  │                                            │
       │  │  方案问题 → 回 Planner 修订方案            │
       │  └─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PR 阶段（窗口 4）                         │
└─────────────────────────────────────────────────────────────────┘

  [PR Review Agent]  读取 pr-review.md + PR + diff + 主干代码
       │  检查：兼容性、架构破坏、兜底 Bug
       │  ┌────────────────────────────────────────────┐
       │  │  发现问题 → 标记并转回审查 → 修复闭环     │
       │  │  通过 → [开发者] 合并 PR                   │
       │  └────────────────────────────────────────────┘
```

### 4.2 文字说明

#### 开发阶段（窗口 1‑3）

1. **开发者准备输入** — 将任务描述和项目系统设计文档一并提供给 Plan Agent 窗口。
2. **Plan Agent** — 读取 `planning.md` 规则、系统设计文档和任务描述，输出一份完整的实现方案。它不执行代码，不审查代码。
3. **开发者中转** — 将 Plan Agent 输出的实现方案传入 Coding Agent 窗口。
4. **Coding Agent** — 读取 `coding.md` 规则和方案，在本地项目工作区中编码、编写测试（测试依据系统设计文档）、执行测试，测试通过后执行 `git add` + `git commit` 提交到本地仓库。最后输出工作完成情况。
5. **开发者中转** — 通知 Review Agent 窗口开始审查。
6. **Review Agent** — 读取 `review.md` 规则、原始方案和 Coding Agent 的工作完成情况，审查本地仓库中的代码。审查结果分三种走向：
   - **通过** → 开发者执行 `git push` 并发起 PR，进入 PR 阶段。
   - **实现偏差 / Bug / 规范问题** → 输出结构化评审报告（问题位置、错误原因、修复方向建议），连同原始方案一起发回 Coding Agent 窗口进行修复。修复后重新走提交 → 审查流程。
   - **方案层面错误** → 评审指出方案缺陷根源，开发者回到 Plan Agent 窗口传入（任务 + 旧方案 + 设计问题），让 Plan Agent 修订方案，再走新方案 → Coding → Review 流程。

#### PR 阶段（窗口 4）

7. **开发者触发 PR Review** — `git push` 成功后发起 Pull Request。
8. **PR Review Agent** — 读取 `pr-review.md` 规则，执行以下步骤：
   - `git fetch origin` 拉取远程所有分支最新快照
   - 创建本地跟踪分支：`git checkout -b feat/xxx origin/feat/xxx`
   - 生成 diff：`git diff origin/main...HEAD`
   - 读取项目系统设计文档、PR 描述、diff 清单
   - 按需读取 origin/main 原始文件与 feature 分支文件，双向对比
   - 评估：兼容性、架构破坏、与主干现有逻辑是否冲突
9. **审查结果**：
   - **发现问题**（含 Review Agent 阶段未发现的代码 Bug）→ 标记并转回开发阶段的审查闭环，不直接拦截或修复。
   - **通过** → 开发者合并 PR（Squash and Merge）。

---

## 5. 窗口分工细则

| 窗口 | 角色 | 读取的规则文件 | 执行操作 | 输出内容 |
|------|------|---------------|---------|---------|
| 窗口 1 | Plan Agent | `planning.md` | 读系统设计文档 + 任务 → 出方案 | 实现方案 |
| 窗口 2 | Coding Agent | `coding.md` | 编码 → 写测试 → 测试验证 → git add + git commit | 工作完成情况报告 |
| 窗口 3 | Review Agent | `review.md` | 审查代码 → 区分问题类型 | 结构化评审报告 |
| 窗口 4 | PR Review Agent | `pr-review.md` | fetch → 建本地跟踪分支 → diff → 双向对比审查 | PR 审查结果 |

---

## 6. 分支策略

采用轻量化 **GitHub Flow**：

| 项目 | 规则 |
|------|------|
| 常驻主干 | `main`（永久可运行，受保护） |
| 分支来源 | 所有工作分支从 `main` 创建，合并后销毁 |
| 合并方式 | Squash and Merge |

**分支命名规范：**

| 前缀 | 用途 |
|------|------|
| `feat/xxx` | 新功能 |
| `fix/xxx` | Bug 修复 |
| `hotfix/xxx` | 线上紧急修复 |
| `refactor/xxx` | 代码重构 |
| `docs/xxx` | 文档更新 |
| `exp/xxx` | 临时实验 |

**标准操作流程：**

```bash
# 1. 进入项目根目录
cd ~/code/your-project

# 2. 切换到主干，同步最新代码
git checkout main
git pull origin main

# 3. 创建新功能分支
git checkout -b feat/xxx

# 4. 开发完成
git add .
git commit -m "清晰描述改动"

# 5. 推送远程
git fetch origin
git push -u origin feat/xxx

# 6. 预览 PR 差异
git diff origin/main...HEAD
```
