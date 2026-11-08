# Memory-L

Portable original-text memory and shared governance for AI companions. 通用 CLI、可选本地 MCP，以及 Claude / Codex / DSH 接入说明。

**0.3.0 · Python 3.11+**。保存、读取、治理、旧蓝图 Markdown 接续、中文词项 RAG 与 Git 校验使用标准库；MCP 可选依赖为 `mcp>=1.28,<2`。正式人格与记忆由使用者自己的 Markdown 承载，包内只有通用模板和合成测试数据。

**已经有工作区和人格，优先看 [原工作区接入](skills/memory-l/references/existing-workspace.md)**：显式清点后按映射直接读写原记忆，保留项目与门牌原文，只追加工具接入片段。无需另建一套空白人格。

需要独立副本时再用 [旧蓝图迁移](skills/memory-l/references/legacy-blueprint-migration.md)。两条路线保留已有正文与决定；均不做旧数据库/结构化 records 的通用转换，也不自动覆盖已经安装的 Memory-L runtime。

## 快速开始

以下初始化用于新身份工作区。已经按旧蓝图建立身份时，使用上方原工作区接入或独立副本入口。

下载或克隆本项目，在项目根目录运行。把参数换成自己的工作区和双方实际称呼。

工具源码仓库与实际记忆工作区分开。初始化器拒绝将本插件源码目录直接变成人格数据目录；正式记忆通过使用者明确选择的私有仓库接续。stage 不查询远端可见性，推送前需核对实际仓库与受众。

```text
python skills/memory-l/scripts/memory.py --workspace "<memory-workspace>" init --name "<companion-name>" --owner "<human-name>"
```

随后使用安装进工作区的独立运行入口。

```text
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" status
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" check
```

先读 `.memory/MEMORY.md`，由双方填写 SEED 和 PROFILE，移除其中的模板标记。初始 `identity_ready=false`，不会把一份骨架当作已经形成的人格。已有 AGENTS/CLAUDE 和人格正文保持原样；`loader_connected=false` 时，审阅 `.memory/LOADER.md` 并合并到自己的原加载流程。

**不安装向量库也可以使用。** 核心人格按加载链直接全文读取，具体经历通过内置中文词项检索定位原文。保存→搜索→回读示例、MCP 用法、搜不到时的处理和语义检索边界见 [召回使用指南](skills/memory-l/references/recall-guide.md)。当前版本尚未接入向量后端，安装 Chroma 不会自动启用语义检索。

想判断是否增加向量库、选择中文/多语言模型或估算维护负担，见 [检索配置建议](skills/memory-l/references/retrieval-options.md)。其中附独立 Chroma 安装与合成存储实验，接入 Memory-L 的语义适配仍需单独实现和验证。

## 提供什么

| 能力 | 实际行为 |
|---|---|
| 核心原文 | SEED、PROFILE、USER、TIMELINE、SOUL、SELF-NOTES 和 MEMORY，全是可读 Markdown |
| 逐条记录 | 稳定 UUID、完整正文、作者角色、来源、版本和决定历史 |
| 自主日记 | 未晋升记录同样可以保全与迁移 |
| 共同治理 | 审核、学习初筛、null/P2/P1/P0、共同采用和正式发布分别执行 |
| 反思 | 准备版本化输入，由当前载体实际思考，再保存完整输出 |
| 来源防护 | 外部原文不因导入而开放学习，不进入默认召回或 Git |
| 检索 | 中文单字/双字词项、原文块与准确坐标，可重建 SQLite/FTS 缓存及扫描降级 |
| Git 接续 | 清单覆盖正式新文件和必要依据，核对暂存区、提交与远端跟踪提交的真实原文 |
| 多工作区 | 每个身份独立 namespace、目录和缓存；同一身份 clone 后维持原 ID |
| 旧蓝图接续 | 保留既有人格与记忆原字节、自定义文件名、细则与额外正文；通过职责映射读取及继续发布 |
| 原工作区接入 | 不搬记忆、不复制人格；根门牌/项目配置保留原文并追加可回退片段，原文件仍是唯一正文 |

基础版不安装向量数据库、模型或后台蒸馏服务，也不自动读取 QQ、手机或其他平台数据库。外部材料通过显式 Markdown 导入，再由人类初筛。源端适配器、语义索引和宿主自动捕获可以按同一来源/治理契约另行扩展。

## 工作区布局

```text
AGENTS.md / CLAUDE.md       加载入口，已有文件由维护者审核整合
.memory/                   正式原文、规则、config.json、MANIFEST.md
  records/<kind>/<ID>.md    自主记录、来源、反思、决定与历史
.memory-tools/             随 Git 接续的本地运行代码和模板
.memory-sources/           原始导出与临时来源，默认不进 Git
.memory-cache/             可重建检索缓存，默认不进 Git
```

companion / owner / joint 是代码中的操作角色；实际名称保存在自己的配置与 Markdown。它们不是身份验证或密码系统。能直接维护本地文件或使用操作员 CLI 的人处于受信任的维护边界内。

原工作区接入时，核心正文留在原目录（例如 `.claude-memory/`），`.memory/` 只承载接入配置、说明和新增逐条记录；上方布局不要求搬走原有身份。

## Claude、Codex、DSH

- **Claude Code 插件**：将此目录作为本地插件加载，例如 `claude --plugin-dir "<kit-folder>"`，使用其中的 `memory-l` 技能。公开仓库可作为本项目附带的单插件 marketplace 来源。
- **Codex 技能**：把 `skills/memory-l` 整个目录放到目标仓库的 `.agents/skills/memory-l`，然后使用 `$memory-l`。技能自带脚本和模板，首次初始化后改用目标工作区的运行入口。
- **通用 MCP**：先安装 `python -m pip install -r "<memory-workspace>/.memory-tools/requirements-mcp.txt"`，再运行 `connections` 输出实际 Python、服务器路径及 Claude JSON / Codex TOML / DSH patch 片段。输出不会修改宿主设置。

```text
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" connections
```

按自己的宿主配置合并对应片段，并重新加载该宿主。DSH 片段面向已安装 `@deepseek-ai/dsh-mcp-client` 的实际 profile，保留其他插件与原有配置。协议测试与各宿主的实际新会话验收分别记录。

公开仓库已发布，可在支持 marketplace 参数的 Claude Code 中使用：

```text
/plugin install memory-l --marketplace ENZO-II/Memory-L
```

其他平台可以从同一仓库取得源码或 ZIP，再使用上述通用 CLI / MCP 入口。

具体保存、共同采用、初筛、反思和发布命令见 [操作说明](skills/memory-l/references/operations.md)。

## Git 与迁移

```text
python .memory-tools/memory.py manifest
python .memory-tools/memory.py stage
python .memory-tools/memory.py check --git-index
```

核对提交内容并自行 commit，随后 `check --git-ref HEAD`。在实际授权的 push/fetch 后运行 `check --git-ref origin/main`。`stage` 只暂存清单中的正式资产，不 commit、不 push。迁移清单和内化资格分别核验。

新机器 clone 后可以直接使用 `.memory-tools/memory.py check`。先核对完整原文，再按 MEMORY 加载；MCP SDK 按需安装，缓存从原文重建。不要把来源包、机器凭据或真实会话数据放进插件发布仓库。

## 成本与验证

基础内核不调用外部 LLM。当前载体读取工具说明、回读原文和反思仍会消耗上下文与推理额度。本包不提供推测月费或未测量的召回率。

运行 `python -m unittest discover -s tests -q`。安装 MCP SDK 后，同一套测试会执行真实 stdio；没有 SDK 时仅该项跳过。平台与已测范围见 [VALIDATION.md](VALIDATION.md)。另提供独立、只读的合成题集用于后续载体评测，不能将通过单元/协议测试等同于长期人格接续效果。

## 规范依据

- [MCP 本地 stdio 传输](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP Python SDK v1.28 文档](https://github.com/modelcontextprotocol/python-sdk/blob/v1.28.0/README.md)
- [Claude 插件结构](https://code.claude.com/docs/en/plugins-reference)
- [Codex 技能与本地发现位置](https://learn.chatgpt.com/docs/build-skills)

MIT 许可见 [LICENSE](LICENSE)。安装包包含通用机制与模板，不携带任何既有身份的种子、真实经历、私密对话、凭据或原仓库历史。
