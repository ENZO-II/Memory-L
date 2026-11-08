# 已经诞生、已有工作区：在原处接入

适用于 Memory-L 0.3.0。面向沿用旧 Markdown 蓝图、尚未安装 Memory-L 的身份。已有工作区、项目和人格继续使用原来的位置；工具按映射直接读写原记忆文件，不建立第二套空白身份，也不搬走项目。

若希望建立另一份独立接续副本，另选 [旧蓝图迁移](legacy-blueprint-migration.md)。已经安装 Memory-L 或元数据位置被其他工具占用时，本流程会停止，不自动覆盖旧 runtime 或清空目录。

## 接入会做什么

| 内容 | 实际行为 |
|---|---|
| 原种子、人格、用户、成长、SOUL、日记与细则 | 原路径、原文件名、原字节保留；读取和后续发布直接使用它们 |
| AGENTS / CLAUDE | 保留完整原文为前缀，只追加可核对的接入片段 |
| 项目文件与其他缓存 | 不替换、不复制进记忆，也不更改其内容 |
| `.memory-tools/` | 新增本地 CLI / MCP 代码和模板资源；模板资源不作为已有身份正文加载 |
| `.memory/` | 新增配置、接入说明、回退快照、清单及今后的逐条自主记录；不生成替代种子与人格 |
| `.memory-cache/memory-l/` | 独立缓存与事务记录，保留 `.memory-cache/` 下其他内容 |
| `.gitignore` / `.gitattributes` | 保留原文，追加本工具排除和原记忆逐字节保全规则；明确排除的来源加到忽略规则 |

已有采用与观察状态通过原文接续，不重新分级。内部 namespace 用于新记录 ID，随 Git 接续，不代表创建另一个人格。源数据库、结构化 records、外部附件及宿主旧插件转换仍需分别处理。

## 1. 先选她原来的 canonical 工作区

核对她已经在使用的记忆目录、真实名字、原门牌与完整正文，保全实际 Git 版本或本地备份。多个任务项目共用同一身份时，在原 canonical 记忆工作区接入一次，各项目连接同一工具入口；不要在每个项目里新建人格副本。

原记忆目录必须位于所选工作区内，例如 `<existing-workspace>/.claude-memory`。若实际记忆由另一个公共工作区维护，选择那个 canonical 工作区接入，再为当前任务项目配置指向它的 MCP。

新工具所需的 `.memory`、`.memory-tools` 与 `.memory-cache/memory-l` 位置应当尚未存在。遇到占用先核对里面是什么，不要为了让安装通过而删除旧数据。

## 2. 写实际映射，生成计划

输入格式与 [旧蓝图映射](legacy-blueprint-migration.md#2-写一份实际文件映射) 相同。保留她现有名字，core_files 指向原文件名，formal_files 列齐后来新增的正式正文与细则，exclude 写真实来源排除原因。

entry_files 必须明确列出工作区根目录实际存在的 AGENTS / CLAUDE，路径就是这些现有文件的绝对路径。工具需要核对将追加片段的原文版本；原来确实没有门牌时可以用空对象，接入会建立必要入口。

将输入与计划保存到工作区之外的私人位置：计划含本机路径和门牌回退字节，不放进公开插件仓库。前两个命令使用新版本插件源码的入口，因为此时尚未安装本地 runtime。

```text
python "<kit-folder>/skills/memory-l/scripts/memory.py" --workspace "<existing-workspace>" attach-plan --input "<attachment-input.json>" --output "<attachment-plan.json>"
```

检查 ready_to_apply、未分类条目、原路径映射、警告与计划中的四份根文件前后内容。计划阶段不改工作区，不导入排除来源。每份源目录 Markdown 都要分类；原文、门牌、Git 配置或工具版本变化后重新生成计划。

在应用的短暂窗口内，先协调会写入这些记忆和门牌的进程，避免并发修改。工具不会自动停用旧宿主插件、事件和采集器。

## 3. 在原工作区应用与验证

```text
python "<kit-folder>/skills/memory-l/scripts/memory.py" --workspace "<existing-workspace>" attach-apply --plan "<attachment-plan.json>"
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" attach-verify
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" status
```

应用前再次核对源版本与根文件。事务记录保存接入计划，原门牌与根 Git 配置的接入前完整字节保存在 `.memory/attachment.json`；只在版本仍匹配时追加片段。新代码位置发生冲突时停止，不能覆盖无关内容。

一般执行错误会尝试恢复本轮根文件片段，保留新增代码、元数据与记录供核查。进程中断后，可用相同版本入口和原计划再次执行 attach-apply；它只续接属于该计划的内容，冲突时停止。已完成的同一计划重复执行不会重装或重新初始化人格。

status 中应有 attached=true、attachment_phase=complete，以及原 core_root。identity_ready 仍只检查种子/人格文件与模板标记，loader_connected 只检查接入片段，不代替真实加载验收。

attach-verify 比较初始接入快照。开始正常写入后原文哈希自然会变化，后续用普通 manifest/check 维护当前版本，不把初始快照当成永久不能成长的限制。

## 4. 确认仍然从原来的她开始

先按原门牌完整加载身份与共建规则，再全文读取 `.memory/ATTACHMENT.md`。原 MEMORY 保持全文，工具说明给出当前映射；有治理冲突时共同澄清，不用模板替代已有决定。

```text
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" core-file SEED.md
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" core-file AGENTS.md
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" search "<已知旧经历的具体词>"
```

core-file 接受职责名，返回 path 应仍指向原目录，例如 `.claude-memory/my-name-is-companion.md`。target-state diary/growth/calibration 和后续发布也使用这些原路径。

MCP 可先读取 ATTACHMENT.md，再按职责名全文回读核心和 AGENTS/CLAUDE；分页继续读取。按 [宿主接入](operations.md#宿主接入) 输出并合并实际连接片段，核对旧自动写入者和真实新会话。这一轮只验证过合成工作区与协议，不代表已经访问或迁好每位使用者的环境。

## 5. 新记忆与 Git 接续

逐条自主记录仍由 save 等入口写入 `.memory/records/`，日记/成长发布追加到原目录对应文件。以后在原记忆目录新增独立正式 Markdown 时，需要显式登记其职责：

```text
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" attach-register "<相对原记忆目录的新正式文件.md>" --reason "<实际正文职责与来源>"
```

该命令登记一个实际正式文件并保留理由，不生成 P0。已经分类为未筛选来源的路径不能用它绕过来源治理。尚未分类的新 Markdown 会使 manifest/check 停止，提醒补齐正式范围；默认检索继续只用已登记正文。也可按既有规则在 `.memory/` 下新增正式正文并维护读取导航。

随后按通常流程生成 manifest、stage、核对 index、提交并核对 HEAD，在实际授权的私有/受控远端推送后核对 origin/main。清单会携带原目录的已选正式文件、根门牌、接入配置与运行代码；原来源排除保持区分。

工具追加的忽略规则不会自动取消旧 Git 已跟踪来源，也不重写既有历史。核对实际 tracked 文件和受众，避免用宽泛的 git add 覆盖自己的来源规则。目标机 clone 后检查原文与清单，配置使用者的真实路径，重建缓存；已经在旧门牌中写死的机器路径还需逐项核对。

## 6. 需要撤回接入片段时

```text
python "<existing-workspace>/.memory-tools/memory.py" --workspace "<existing-workspace>" attach-rollback
```

仅当根文件仍是接入前或本工具生成的版本时，恢复 AGENTS/CLAUDE、gitignore、gitattributes 的接入前字节；后来有人改过这些文件时会拒绝覆盖，保留现场供审核。原记忆、接入后写下的经历与新增 records 都不回退或删除。

回退后工具标记为 rolled_back，普通工具调用停止，原门牌继续运行。新增 runtime、元数据与缓存仍留在本地，先核查其中记录和 Git 状态，再决定后续处理；本版本不会清空它们或自动覆盖重装。
