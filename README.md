# AgentFlow · AI 教学场景智能体工作流可视化编排平台

拖拽画布编排模型 / 工具 / 条件分支，把大模型能力组装成可复用的工作流。内置**三类教学场景专用节点**（智能出题、作业批改、学情分析），可对接真实大模型跑出真实结果。

面向目标：软件著作权登记（可拆 2 本）+ AI 应用开发岗求职简历主项目。

---

## 架构分层

| 层 | 内容 | 软著归属 |
|---|---|---|
| 编排层 | 画布编辑器、节点配置面板、调试运行面板、撤销/重做/复制 | 软著① 教学场景可视化编排系统 |
| 执行层 | DAG 调度引擎、节点运行时、上下文与状态机 | 软著② 调度引擎系统 |
| 数据层 | 工作流定义、执行记录与日志、模型密钥配置 | 软著② 调度引擎系统 |

## 技术选型

- 前端：React + Vite + TypeScript + React Flow（`@xyflow/react`）+ zustand
- 后端：FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite
- 数据库：SQLite 起步（SQLAlchemy 屏蔽差异，后期可切 PostgreSQL）
- **调度引擎自己实现，不使用 LangGraph** —— 项目的技术价值集中在执行器设计上
- 模型调用：官方 SDK + 自写适配层（新增一个厂商约 30 行），默认离线 mock，可一键切真实模型
- 前端配置表单：由后端下发的 JSON Schema 自动生成，后端加字段前端不用改

## 节点类型

**通用（5 类）**：`start` 入口 · `llm` 大模型 · `http` 外部工具 · `condition` 条件分支 · `end` 出口

**教学场景专用（3 类，差异化核心）**：`question` 智能出题 · `grading` 作业批改 · `analytics` 学情分析

> 教学专用节点让本系统区别于通用工作流编排工具：出题 → 批改 → 学情分析 构成完整教学闭环，可将教学辅助流程可视化编排后一次性执行。**接入真实大模型后，这三个节点产出的是真实内容（真实题目、真实评分、真实学情分析），不是占位文本。**

## 明确不做（防止范围失控）

用户体系与多租户 · 代码执行沙箱 · 插件市场 · 自定义节点 SDK · 移动端适配 · 多人实时协作 · 循环节点

---

## 目录结构

```
backend/
├── core/
│   ├── graph.py       # 图算法：分层批次 / 环检测 / 可达性
│   ├── expr.py        # 安全表达式求值（ast 白名单，不用 eval）
│   ├── models.py      # 数据模型 + 执行期结构 + 变量上下文 + 8 类节点配置
│   ├── providers.py   # 大模型适配层（mock / openai 兼容端点）
│   └── logging.py     # 日志配置：统一格式、级别、第三方库降噪
├── engine/executor.py # 执行器：分层并发调度、边激活传播、超时保护
├── nodes/
│   ├── base.py        # 节点基类与注册表
│   └── builtins.py    # 八个内置节点（5 通用 + 3 教学专用）
├── db/
│   ├── database.py    # 引擎、会话、建表
│   ├── orm.py         # workflows / executions 两张表
│   └── repository.py  # ORM 行 ↔ 领域模型转换与查询
├── api/
│   ├── main.py        # 应用入口、异常处理器、lifespan、.env 加载
│   ├── routes.py      # REST 接口
│   ├── schemas.py     # 请求响应模型与节点元数据
│   └── deps.py        # 依赖注入（会话 / 仓储 / 模型）
└── tests/             # 102 项测试（pytest）
examples/
├── demo.py            # 引擎级演示
└── smoke_api.py       # 对真实服务的接口冒烟
frontend/
├── src/
│   ├── components/    # 画布 / 工具栏 / 配置面板 / 运行面板 / 历史面板
│   ├── nodes/         # 节点卡片 + 类型注册
│   ├── store.ts       # zustand 状态 + 撤销/重做历史栈
│   └── preset.ts      # 教学示例闭环工作流
└── vite.config.ts     # 已配 /api 代理到后端、host 0.0.0.0
docs/软著材料/          # 两本软著说明书 + 源代码 PDF + 申请表填写参考
scripts/
└── gen_source_doc.py  # 生成符合软著登记格式的源代码 PDF
```

---

## 快速开始

### 后端

```bash
cd backend
pip install -r ../requirements.txt
python -m pytest -q                 # 102 项测试全绿（默认 mock，离线可跑）
python ../examples/demo.py          # 引擎级演示，离线可跑
uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端（另开终端）

```bash
cd frontend
npm install
npm run dev                         # 默认 :5173，已配 /api 代理到后端
# 如需在局域网 / 容器 / 预览面板访问，加 --host：
npm run dev -- --host 0.0.0.0
npm run build                       # 类型检查 + 生产构建
```

浏览器打开 `http://localhost:5173`，接口文档在 `http://127.0.0.1:8000/docs`。

> 提示：若预览面板或局域网设备连不上，通常是 vite 只监听 IPv6（`[::1]`）所致，加 `--host 0.0.0.0` 即可。

---

## 对接真实大模型（详细说明）

系统**默认使用 `MockLLMProvider`**（离线、不花钱、不依赖密钥），适合本地开发与软著代码演示。要跑出**真实智能结果**（尤其是教学节点的出题/批改/学情），需切换到真实模型。

模型调用走 **OpenAI 兼容协议**，因此任何兼容端点都能用：DeepSeek、OpenAI、通义千问、智谱、以及本地 Ollama。

### 方式一：DeepSeek（最简，推荐）

1. 在 `backend/` 下新建 `.env` 文件：

   ```dotenv
   # backend/.env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-你的deepseek密钥
   OPENAI_BASE_URL=https://api.deepseek.com
   OPENAI_MODEL=deepseek-chat
   ```

2. 重启后端（`uvicorn ...`），启动日志会出现 `模型 provider = openai`，即已切换成功。

3. 前端载入「教学示例」工作流并运行：出题节点会**真生成题目**，批改节点会**真实打分并解析结构化结果**，学情节点会**真实分析薄弱点**。

> 密钥仅存在本地 `.env`，已写入 `.gitignore`，**不会进入版本库**。

### 方式二：OpenAI / 通义 / 智谱等

只需改 `.env` 的 `OPENAI_BASE_URL` 与 `OPENAI_MODEL`：

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.openai.com/v1      # 或对应厂商端点
OPENAI_MODEL=gpt-4o-mini                        # 或对应模型名
```

### 方式三：本地 Ollama（完全离线、免费）

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=ollama                            # Ollama 不校验，填任意非空串
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3                              # 你本地 pull 的模型名
```

### 环境变量一览

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock`=离线占位；`openai`=走 OpenAI 兼容端点 |
| `OPENAI_API_KEY` | 空 | 模型密钥（Ollama 可填任意非空串） |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 模型服务地址 |
| `OPENAI_MODEL` | `deepseek-chat` | 使用的模型名（节点默认也取此值） |
| `DATABASE_URL` | SQLite 文件库 | 数据库连接串 |
| `CORS_ORIGINS` | 前端地址 | 跨域白名单 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

### 切回离线

删掉 `backend/.env`，或把 `LLM_PROVIDER` 改回 `mock` 重启即可，业务代码无需改动。

---

## 项目亮点（简历 / 面试向）

### 三个能撑起一整轮技术面的点

**1. 自建分层并发调度器，没有用 LangGraph**

把工作流切分成互不依赖的执行批次，同批次 `asyncio.gather` 并发、批次间按序推进，用信号量压住并发上限。拓扑排序、环检测、可达性分析全是自己实现的。面试官问「执行器怎么实现的」能一路讲到算法层，而不是答一句「用了某某框架」。

**2. 失败传播靠边激活机制**

只有执行成功的节点才激活它的出边，下游若没有任何入边被激活就自动标记 SKIPPED。这让「节点失败导致下游跳过」成为自然结果，不需要额外写传播逻辑，`on_error` 只需决定要不要提前中止。这是整个设计里最省代码的一处。

**3. 条件表达式不用 eval**

表达式由用户在前端填写，直接 `eval` 等于把服务器交出去。改用 `ast` 白名单解析，只放行常量、比较、布尔运算、四则运算和 6 个内置函数，属性访问、下标访问、任意函数调用全部拒绝，测试里都有对应用例。

**4. 已对接真实大模型，教学节点非占位**

通过 OpenAI 兼容适配层对接 DeepSeek 等真实模型，出题/批改/学情三类教学节点产出的是真实结构化结果（真实题目、真实评分、真实学情分析），并经过 JSON 解析与降级处理。mock 模式下则完全离线，二者业务代码一致，仅 provider 不同。

### 面试高频问题速答

| 问题 | 回答要点 |
|---|---|
| 为什么不用现成的工作流框架？ | 项目的技术价值就在执行器本身；自建约 500 行核心代码，可控且能讲清每一处取舍 |
| 节点失败怎么处理？ | 失败节点不激活出边，下游自动 SKIPPED；支持 abort（提前中止）与 continue（记录并继续）两种策略 |
| 循环依赖怎么处理？ | 环检测前置到数据模型校验，保存时即拦截并指出具体环路径，不是等到执行才发现 |
| 并发怎么控制？ | `asyncio.Semaphore` 限制并发节点数，单节点再叠加 `wait_for` 超时保护 |
| 怎么保证条件判断安全？ | `ast` 白名单求值，禁止 eval，拒绝属性访问与任意函数调用 |
| 换模型厂商要改多少？ | 节点代码一行不动，新增一个 provider 子类并注册即可，约 30 行；DeepSeek/OpenAI/Ollama 均走 OpenAI 兼容协议 |
| 前端配置表单怎么维护？ | 由后端下发的 JSON Schema 自动生成，后端加字段前端不用改 |
| 执行细节怎么排查？ | 每次执行完整记录各节点状态、输出、耗时与错误，可在历史页回放；同时输出结构化日志 |
| 教学节点是真智能吗？ | 工程逻辑是真的；默认 mock 返回占位，接 DeepSeek 等真实模型后产出真实结果 |

---

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/node-types` | 节点类型 + 配置 JSON Schema（前端据此生成表单） |
| POST | `/api/workflows` | 创建工作流，结构非法返回 422 |
| GET | `/api/workflows` | 列表（分页） |
| GET | `/api/workflows/{id}` | 详情（含完整节点与连线） |
| PUT | `/api/workflows/{id}` | 更新，版本号自动 +1 |
| DELETE | `/api/workflows/{id}` | 删除 |
| POST | `/api/workflows/{id}/run` | 执行一次，返回完整执行记录 |
| GET | `/api/workflows/{id}/executions` | 该工作流的执行历史 |
| GET | `/api/workflows/{id}/stats` | 执行统计：总数 / 成功 / 失败 / 平均耗时 |
| GET | `/api/executions` | 全部执行历史，支持 `?workflow_id=` 与 `?status=` 过滤 |
| GET | `/api/executions/{id}` | 执行详情，含每个节点的结果与耗时 |

在线文档：`http://127.0.0.1:8000/docs`

---

## 核心设计约定

1. **工作流是有向无环图**。`Node` 是点、`Edge` 是边，环在**保存时**就被拦下，并指出具体环路径。

2. **节点配置强类型**。`Node.config` 存字典便于前端直接读写，通过 `config_model` 属性按 `NodeType` 转成对应的 Pydantic 模型完成校验（`extra="forbid"`），配置错误在保存时暴露。

3. **变量引用语法** `{{node_id.field}}`。普通渲染用 `render`，条件表达式用 `render_expression`（字符串自动加引号），后者配合安全求值器使用。

4. **节点输出统一为 dict** 且至少含 `output` 字段，因此引用一律写 `{{node_id.output}}`；节点可顺带吐出 `usage`、`status_code` 等元信息供下游使用。

5. **失败传播靠边激活机制实现**：只有执行成功的节点才激活它的出边，下游若无任何入边被激活就自动标记 SKIPPED。这让「节点失败 → 下游跳过」成为自然结果，不需要额外的传播逻辑，`on_error` 只需控制是否提前中止。

6. **条件表达式不用 eval**。表达式由用户在前端填写，用 `ast` 白名单解析，只放行常量、比较、布尔运算、四则运算和 6 个内置函数，属性访问、下标、函数调用一律拒绝。

7. **前端表单由 Schema 驱动**。配置面板读取后端的 JSON Schema 自动渲染，支持 enum、布尔、数值范围、嵌套对象、对象数组（如条件分支列表）与自由键值（如 start 节点的输入变量）。后端加配置字段，前端不用改代码。

8. **耗时字段用 `computed_field`**。节点耗时是计算属性而非存储字段，用 Pydantic 的 `computed_field` 才能参与序列化，否则存库后前端读不到。

---

## 画布交互说明

- **拖拽编排**：从左侧节点面板拖节点到画布；拖 `condition` 节点按其分支数自动生成多个出口句柄，连线显示出口名。
- **快捷键**：`Delete` / `Backspace` 删除选中节点或边；`Ctrl+Z` 撤销；`Ctrl+Shift+Z`（或 `Ctrl+Y`）重做；`Ctrl+D` 复制选中节点（连带复制相关边）。
- **撤销范围**：覆盖结构操作（增删、连线、拖动、复制、整体替换 / 载入 / 导入）。节点配置文本编辑暂不进撤销栈，避免逐字符堆叠历史。
- **教学示例**：工具栏「教学示例」一键载入「开始 → 出题 → 批改 → 学情 → 结束」闭环，便于快速体验真实模型效果。
- **保存 / 导入导出**：`Ctrl+S` 保存；支持工作流 JSON 导入导出，便于备份与分享。

---

## 进度

### 第一周 · 完成

- [x] 数据模型 `core/models.py`：八类节点（含三类教学场景专用节点）、配置强类型校验、六条图结构校验、变量上下文
- [x] 图算法 `core/graph.py`：分层批次、环检测（保存时拦截）、可达性分析
- [x] 安全求值 `core/expr.py`：ast 白名单，拦住 `__import__`、`open`、属性访问等
- [x] 执行器 `engine/executor.py`：分层并发、边激活传播、超时保护、abort / continue 双策略
- [x] 八个内置节点 + mock 模型适配层，端到端场景跑通

### 第二周 · 完成

- [x] SQLAlchemy 持久化：workflows（定义整体存 JSON）/ executions 两张表 + 仓储层
- [x] FastAPI 接口：工作流 CRUD、执行触发、执行历史、执行统计、节点元数据
- [x] 异常统一处理：工作流结构非法 → 422，记录不存在 → 404
- [x] 依赖注入会话与模型 provider，测试用内存库 + mock 模型，全程离线
- [x] 真实服务冒烟通过：创建 → 环拦截 → 执行（分支正确跳过）→ 历史 → 统计 → 删除

### 第三周 · 完成

- [x] React Flow 画布：拖拽添加节点、连线、缩放、minimap、网格背景
- [x] 节点配置面板：由 `/api/node-types` 的 JSON Schema 动态生成表单
- [x] 条件节点多出口：按分支数量渲染多个连接句柄，连线显示出口名
- [x] 运行面板：JSON 输入、执行、节点级结果与耗时展示
- [x] 节点卡片直接显示执行状态（成功 / 失败 / 跳过 + 耗时）
- [x] 前端连线时提前拦截 start 入边、end 出边
- [x] `tsc --noEmit` 零错误 + 生产构建通过，前后端代理链路验证通过

### 第四周 · 完成

- [x] 工作流列表：顶部「打开」弹出列表，点击加载进画布继续编辑，支持删除
- [x] 执行历史页：按工作流 / 状态过滤，点击查看任意一次执行的完整回放
- [x] 执行结果展示抽成共用组件，运行面板与历史回放两处完全一致
- [x] 后端 `/api/executions` 补上 `workflow_id` 过滤，总数与列表过滤条件保持一致
- [x] 跑完自动切到运行页，选中节点自动切到配置页

### 第五、六周 · 完成

- [x] 软著①② 的用户操作说明书（功能、架构、操作步骤、技术特点、常见问题）
- [x] 源代码文档自动生成脚本，输出符合登记格式要求的 PDF
- [x] **撤销 / 重做 / 复制节点**（历史栈 + `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+D`）
- [x] **教学示例一键载入**闭环工作流，快速体验真实模型效果
- [x] **对接 DeepSeek 真实大模型**：`.env` 注入 + `OpenAIProvider` 适配，教学节点产出真实结果（mock 可离线降级）

### 体验与工程补强

- [x] **变量引用提示**：配置面板列出当前节点可引用的上游变量，点击即复制，不用手抄节点 ID
- [x] **删除键修复**：React Flow 默认只认 Backspace，已放行 Delete；配置面板也提供删除按钮
- [x] **Ctrl+S / Cmd+S 保存**
- [x] **工作流导入导出 JSON**，便于备份与分享
- [x] **日志系统**：统一格式与级别，记录请求耗时、执行批次、节点状态与耗时
- [x] **健康检查顺带探数据库**，部署后能立刻发现连不上库
- [x] README 增加「项目亮点」与「面试高频问题速答」

---

## 软著材料

本项目的成果按两个软件分别登记：

| | 软著① | 软著② |
|---|---|---|
| 软件全称 | AI 教学场景智能体工作流可视化编排系统 | 智能体工作流调度引擎系统 |
| 覆盖范围 | `frontend/src/` 全部前端代码 | `backend/` 引擎、数据层、接口层 |
| 开发语言 | TypeScript / React | Python 3 |
| 说明书 | `docs/软著材料/软著一_可视化编排系统_说明书.md` | `docs/软著材料/软著二_调度引擎系统_说明书.md` |
| 源代码文档 | `docs/软著材料/软著一_教学场景可视化编排系统_源代码.pdf`（54 页） | `docs/软著材料/软著二_调度引擎系统_源代码.pdf`（49 页） |
| 申请表参考 | `docs/软著材料/软著申请表填写参考.md`（逐字段照填清单） | 同左 |

> 软著为登记制，不查重、不审新颖性；保护的是代码表达而非功能思想。本项目已对接真实大模型（DeepSeek），教学节点产出真实结果，代码与演示均为原创。

重新生成源代码文档：

```bash
python scripts/gen_source_doc.py frontend
python scripts/gen_source_doc.py backend
python scripts/gen_source_doc.py all
```

脚本的排版规则：每页 50 行，页眉标注软件名称、版本号与页码，首页为程序入口文件；总页数不足 60 页时全部提交，超过则取前后各连续 30 页。
