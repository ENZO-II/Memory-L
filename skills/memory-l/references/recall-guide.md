# 不安装向量库，怎样使用记忆？

适用于 Memory-L 0.1.x 至 0.3.x。当前版本提供标准库 CLI、中文词项 RAG 和可选 MCP。语义向量检索尚未接入；安装 Chroma 或 embedding 模型不会自动开启这项能力。已有工作区优先按 [原工作区接入](existing-workspace.md) 接续；原加载链继续，另读 ATTACHMENT。独立迁移副本先读 KIT-INTEGRATION 与映射中的原 MEMORY。

## 先理解两种读取

**加载自己**：每次会话先读 `.memory/MEMORY.md`，按顺序全文读取 SEED、PROFILE、USER、TIMELINE、SOUL，再用 `context --purpose profile` 读取合格的人格补充。分页和截断继续回读。SELF-NOTES 是按需翻阅的日记。这条加载链直接读取 Markdown，不依赖检索排名，也不依赖向量库。

**回想具体经历**：需要过去的日记、决定或工作记录时，用 `search` 定位相关原文，再按记录 ID 或文件坐标回读。召回只是提供材料，是否采用某种理解仍看实际治理决定。

先按 [README 快速开始](../../../README.md#快速开始) 初始化独立记忆工作区，并共同填写自己的种子与人格。`identity_ready=false` 表示模板尚待填写；已有加载门牌时，按 LOADER 说明审核整合。插件源码目录不能直接充当私人记忆工作区。

## CLI：保存、搜索、回读

以下 `<memory-workspace>` 要替换成记忆工作区的实际绝对路径。基础 CLI 只需 Python 3.11+；无需安装数据库服务、embedding 模型或外部模型 API。

若想先验证一遍流程，把下面的合成示例写入工作区内的 `demo-input.json`。它不是一条真实经历，正式使用时换成自己的实际内容和操作 ID。

```json
{
  "kind": "work",
  "body": "合成示例：迁移到新机器后，先核对 Markdown 原文清单，再重建检索缓存。",
  "operation_id": "demo-recall-001",
  "metadata": {"title": "合成示例：新机器迁移", "carrier": "cli-demo"}
}
```

```text
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" save --input "<memory-workspace>/demo-input.json"
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" search "迁移 原文清单" --limit 5
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" read "<返回的完整record_id>"
```

`save` 的输出也带完整 `id`。重复保存同一请求保持 operation_id 和内容一致；另一条经历使用新的稳定 ID。搜索结果在 `items` 中，包含原文块 `text`、文件 `file`、行号 `line`，逐条记录还带 `record_id`、来源和治理标签。排序分数不代表事实可信度或内化程度。

有 record_id 时用 `read` 回读全文与历史；普通 Markdown 按文件和行号展开上下文。仅看短片段不足以判断条件、说话者和前因后果。

## MCP：在对话中使用

MCP 是可选接入方式。安装其依赖、用 `connections` 生成片段并按 [宿主接入](operations.md#宿主接入) 合并配置后，用户可以自然地说：“找一下我们上次讨论迁移的记录，读原文后再回答。”由载体实际调用工具，安装本身不会自动触发召回。

典型流程是调用 `memory_l_search`：

```json
{"query": "迁移 原文清单", "limit": 5, "include_raw": false, "refresh": false}
```

再把具体结果的 record_id 传给 `memory_l_read`；核心文件也可用 `memory_l_core_file` 分页读取。用户不必每次手写命令。没有 MCP 的平台，可通过允许执行本地命令的载体使用同一 CLI；只能聊天、无法读取文件或调用本地工具的平台需要另外的接入方式。

## 默认检索实际上做了什么

搜索在本工作区的正式 `.memory/` 中定位材料，中文按单字与相邻双字词项匹配，英文等使用词项匹配。结果结合词项重合、标题和原文短语匹配排序，不使用 embedding。索引自动建立在 `.memory-cache/ordinary.sqlite`，后续查询核对来源变化。

Python 的 SQLite/FTS 可用时使用本地全文缓存，无需单独运行服务器；SQLite/FTS 不可用或缓存发生数据库错误时，转为扫描 Markdown。返回 `mode=direct_lexical_rag` 和 diagnostics 时表示正在使用扫描降级，原始记忆仍由 Markdown 保存。大工作区的扫描耗时需实际测量。

默认召回包含核心正文、符合用途的自主记录和已准入材料。自主日记可以尚未晋升；外部材料则要经过真实的人类初筛。仅导入或普通审核确认不会让整批端口原文进入默认检索。

## 搜不到时如何处理

1. 核对 `status` 中的工作区路径，以及目标正文是否确实保存在该工作区。对明确的条目可先 `list <kind>`，再按 ID 回读。
2. 用人名、项目名、事件名或原文可能出现的词分别查询。例如先查“迁移”，再查“原文清单”，而不是只依赖一句抽象提问。载体可以根据实际结果尝试同义表达，当前检索器没有自动语义改写能力。
3. 核对来源状态、学习选择和生命周期。材料可能因尚未初筛、撤回、拒绝或到期而不适合当前用途。
4. 需要强制刷新索引时使用下列命令。缓存错误会自动尝试扫描降级；不要为修复缓存删除正式 Markdown。

```text
python "<memory-workspace>/.memory-tools/memory.py" --workspace "<memory-workspace>" search "迁移" --refresh
```

用户明确要求审阅来源档案时，可以使用 `search "<来源问题>" --include-raw` 或 `context --purpose archive`。档案入口扩大的是查阅用途，不授予学习或内化资格；不要把它作为默认回答搜不到时自动开启的开关。它也不承诺逐条返回全部内部管理记录。

## 什么时候需要语义检索

路线选择、本地 Chroma 安装实验、模型候选与成本评估见 [检索配置建议](retrieval-options.md)。

| 需求 | 当前版本的处理 |
|---|---|
| 完整加载核心人格和记忆 | 直接读取原文，无需向量库 |
| 查具体名字、事件、关键词 | 使用现有中文词项 RAG，按结果回读 |
| 问题与原文表达差异很大 | 尝试不同词项和分类回读；仍可能漏召回 |
| 自动按语义找同义、隐含关联 | 尚未实现，需要语义后端扩展与实际评测 |

是否扩展，依据自己的已知问题与原文核对结果来判断。当前通过工程和协议验证，不代表已经测得某种召回率。

如要自行接入 Chroma 等向量后端，需要实际编写建索引、更新、查询与读取时核验的适配逻辑。至少沿用以下契约：

- Markdown 是原文；向量与 embedding 属于可重建派生数据，保留来源 ID、原文坐标和版本哈希。
- 默认索引与查询都遵守相同的来源初筛、用途、撤回和生命周期约束；未初筛的端口原文不能借向量层进入默认召回。
- 原文修改、删除和状态变化后，更新索引，并在返回结果时核验当前来源。
- 模型、索引版本及实际资源开销可核对；依赖不可用时保留现有词项检索入口。
- 用已知答案和原文依据比较扩展前后的召回、误召回、上下文与成本，再决定是否采用。

以上是扩展要求，当前发行版没有向量安装向导或可启用的 Chroma 配置。基础 CLI 不产生独立模型 API 调用；当前载体回读、反思和回答仍消耗其上下文与推理额度。

## 换机器后

通过自己选择的受控仓库携带正式原文、配置和 `.memory-tools`，先运行 `check` 核对原文，再按 MEMORY 完整加载。`.memory-cache` 无需上传，首次搜索可从 Markdown 重建。MCP 依赖与宿主设置在新机器按需安装和配置。完整 Git 流程见 [迁移与新增文件](operations.md#迁移与新增文件)。

一次基本验收可以检查：核心文件能完整读完；上述合成记录能保存、搜索和按 ID 回读；未初筛的外部材料没有出现在默认召回；新机器的原文清单检查通过。真实载体在日常对话中是否主动、恰当地回读，需要另外观察。
