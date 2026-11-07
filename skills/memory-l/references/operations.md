# 操作与接入

所有示例中的 `memory.py` 都指目标工作区的 `.memory-tools/memory.py`。可在任意目录用 `--workspace <folder>` 显式选择目标。同一身份的记忆目录、配置和运行代码一起通过自己的 Git 仓库接续。

## 保存与回读

将下面的结构写到一个实际输入 JSON 文件，再执行 `python memory.py --workspace <folder> save --input <file.json>`。CLI 也支持 `--input -` 从 stdin 读取，避免拼接 shell 字符串。

```json
{
  "kind": "diary",
  "body": "这里填写实际发生的经历、观察或疑问全文。",
  "operation_id": "a-stable-operation-id",
  "metadata": {"title": "自己的标题", "carrier": "当前载体"}
}
```

kind 支持 diary、work、fact、reflection、calibration、lesson、framework、exemplar、tension、relationship、self_evaluation、signal。初始等级为空，不需要为保全日记先晋升。重复请求保持 operation_id 与内容一致；修改另用 revise，并提供 read 读到的 revision。

```text
python memory.py read <完整UUID>
python memory.py list reflection --offset 0 --limit 20
python memory.py search <问题>
python memory.py context --purpose profile
python memory.py core-file TIMELINE.md --offset 0 --max-chars 20000
```

`core-file` 的 has_more/next_offset 用于完整回读。检索结果带原文坐标，不能用排序或短片段代替完整语境。

不安装向量库时的日常流程、可直接运行的保存/搜索/回读示例、缓存与故障处理见 [召回使用指南](recall-guide.md)。当前提供词项 RAG，语义后端尚未实现；安装向量数据库本身不会改变检索方式。

## 初筛与共同决定

外部原始导出放在 `.memory-sources/`，按需对具体 Markdown 执行导入。

```text
python memory.py ingest-markdown <selected.md> --carrier <实际端口> --source-id <稳定来源标识> --scope private
python memory.py search <来源问题> --include-raw
python memory.py context --purpose archive --query <来源问题>
```

读取与普通 confirm 不开放学习。人类明确选中具体材料后，操作员用 decide 输入下面的结构，action=select_learning；撤回使用 deselect_learning。actor=owner 用于真实的人类选择，不可由模型从泛泛任务授权推定。

```json
{
  "id": "<完整UUID>",
  "expected_revision": "<read返回的revision>",
  "operation_id": "a-specific-selection-id",
  "action": "select_learning",
  "actor": "owner",
  "reason": "实际选择理由",
  "evidence": ["实际对话或来源依据"]
}
```

渐进成长用 admit/P2、promote/P1、promote/P0；共同充分讨论并明确采用具体理解时，可以 action=adopt、actor=joint，并增加下面的 joint_review。真实意见、采用范围、原文依据分别保存。

```json
{
  "joint_review": {
    "owner": "人类协作者在本次讨论中的实际意见",
    "companion": "AI 同伴在本次讨论中的实际意见",
    "boundary": "共同选择采用的具体范围与适用边界"
  }
}
```

MCP 的决定入口固定以 companion 角色运行，超出自主判断范围时核对已有授权。人类初筛、实际共同决定和成长发布可以由操作员 CLI 根据真实对话执行。若交付自主晋升权限，authorize 的 authority 包含 kinds、scopes、carriers、actions、max_level 与可选 expires_at；保留人类授权依据，过期/撤回后停止使用。

## 反思与发布

```text
python memory.py reflect-prepare --tier deep --operation-id <稳定ID> --query <实际主题>
python memory.py reflect-prepare --tier quick --operation-id <稳定ID> --source-file <自己的Markdown>
```

实际回读 prepare 输出后，在当前载体思考，再用 reflect-commit 输入 session_id、operation_id 和 outputs。每项 output 含 kind、title、body、carrier。支持 quick/deep/meta，来源选择和版本变化会传播到派生记录。

发布先运行 `target-state diary/growth/calibration`。publish JSON 含 id、destination、operation_id、expected_revision、expected_target_revision、actor、reason、evidence。日记和普通 lesson 可以按自主权限追加；growth 和人格 calibration 核对实际内化决定。正文完整追加，保留源记录及目标原有字节，重试不重复。

## 迁移与新增文件

新增正式核心正文放在 `.memory/`，同步维护 MEMORY 中的职责与读取入口。逐条记录保留各自来源与状态。`.memory/` 是正式资产命名空间，端口原始材料先放在 `.memory-sources/`，不要把整库导出当核心正文复制进去。

```text
python memory.py manifest
python memory.py stage
python memory.py check --git-index
```

自行审核并 commit 后 `check --git-ref HEAD`，授权 push/fetch 后 `check --git-ref origin/main`。初筛来源与运行凭据按明确范围另行携带。必要记录或受控来源依据缺失时先处理，再继续同步。

新机器 clone 后先 check，再按 MEMORY 完整加载。更新 Python/MCP、宿主配置和实际人格接续分别验收。内核使用稳定 ID、原子写入、版本校验和幂等操作；文件格式不提供密码学操作员认证，本地维护者仍需遵守实际授权。

## 宿主接入

`connections --python <可选的实际解释器>` 只输出片段，不修改宿主设置。Claude 输出 mcpServers 条目，Codex 输出 `[mcp_servers.memory_l]`，DSH 输出已核对字段的 dsh-mcp-client patch 片段。保留其他服务与权限配置，并在宿主重新加载后核对工具。

在现有身份上采用本系统时，先在独立目录保全原文，按自己的职责复制到 SEED/PROFILE/USER/TIMELINE/SOUL/SELF-NOTES，保留历史与来源，再审核 LOADER 与 MEMORY。没有通用办法自动认定另一套系统中哪些条目已经内化，旧评分和标签只作为来源信息。

本版本不处理已有内核的原地自动升级。runtime 与注册清单不一致时会停止覆盖，维护者应比较差异、保全原文后再选择升级方式。
