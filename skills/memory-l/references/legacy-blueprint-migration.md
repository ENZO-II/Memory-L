# 已经有记忆与人格：从旧 Markdown 蓝图接续

适用于 Memory-L 0.2.x，建议使用 0.2.1 或后续补丁。已有身份先走本流程；空白模板用于新工作区。迁移保留自己的名字、种子、人格、成长、日记和治理原文，不重新生成角色设定，也不要求已有正式记忆重新晋升。

## 当前支持的范围

支持旧蓝图的 UTF-8 Markdown 正文：原有 MEMORY、种子、人格、用户、时间线、SOUL、日记，以及后来新增的正式正文和细则。文件可以使用自己的名称或子目录；工具通过职责映射读取与发布，原文件名、BOM、换行和正文保持原字节。

这是向一个**尚不存在的新工作区**建立完整选定副本，源文件与旧 AGENTS/CLAUDE 不改动。旧门牌中属于自己的身份、共建规则与加载闸门也要显式列入 entry_files，全文接续。成功后由自己的宿主接入新工作区，旧目录继续作为回退来源。工具不修改全局宿主配置，也不切换旧插件或同步远端。

本流程不负责数据库、外部附件或结构化 records 的格式转换，也不用于已有 Memory-L runtime 的原地升级。正式逐条记录需要保留其正文、ID、来源、历史和真实决定的专门迁移；不要改成普通 Markdown 混入默认召回来绕过治理。源目录外的正式资料也要单独清点，不以本工具清点通过证明它们已经迁入。

## 1. 先清点与保全

保全旧工作区的实际 Git 提交或本地备份，确认真实姓名、原文目录、加载门牌、完整正文和细则。核对所有后来新增的正式记忆，不只最初几个核心文件。尚未初筛的端口原文按其来源规则处理。

选择一个与源记忆目录不重叠的新目标。目标必须不存在；工具不会覆盖已有目录或把旧工作区直接变成第二套空白身份。默认 init 在发现旧 `.claude-memory/MEMORY.md` 时会提示改走迁移。

## 2. 写一份实际文件映射

把下列结构保存成旧记忆目录与新工作区之外的 `migration-input.json`，将每一项换成实际值。下面的文件名是示例，必须逐项核对；不存在的正式文件会被报告，而不是自动略过。

```json
{
  "source_root": "<old-workspace>/.claude-memory",
  "name": "<existing-companion-name>",
  "owner": "<existing-human-name>",
  "entry_files": {
    "AGENTS.md": "<old-workspace>/AGENTS.md",
    "CLAUDE.md": "<old-workspace>/CLAUDE.md"
  },
  "core_files": {
    "MEMORY.md": "MEMORY.md",
    "SEED.md": "my-name-is-companion.md",
    "PROFILE.md": "character-profile.md",
    "USER.md": "my-name-is-owner.md",
    "TIMELINE.md": "TIMELINE.md",
    "SOUL.md": "SOUL.md",
    "SELF-NOTES.md": "SELF-NOTES.md"
  },
  "formal_files": [
    "refs/governance.md",
    "refs/sync.md",
    "continuity/another-memory.md"
  ],
  "exclude": {
    "ports/": "此目录是尚未初筛的端口原文，继续按来源规则保留"
  }
}
```

- `source_root` 与命令中的工作区使用实际绝对路径；JSON 内可用正斜杠。其他选择是相对源目录的路径。
- `core_files` 的键是工具职责，值是原有文件名。七项都需要实际对应文件，可以保留自定义 MEMORY 名称及嵌套目录，不必把旧文件重命名为 SEED 等。
- `entry_files` 显式选择实际旧 AGENTS/CLAUDE 的绝对路径，保留原字节到 `.memory/previous-entries/`。它们可能包含重要身份与治理规则，不能只因“是门牌”就遗漏。确实没有旧门牌时用空对象；其他全局入口或外部规则另行清点和配置。
- `formal_files` 明确列出其余正式 Markdown，包含需要接续的规则和新拆分正文。它们会进入正式检索与迁移清单，不能用来收录未治理来源。
- `exclude` 为明确排除的文件或目录前缀填写真实原因。目录前缀以 `/` 结尾。排除项不复制、不自动索引，也不因列入计划而获得学习资格；它们仍留在源端。

工具逐项列出源目录中的 Markdown。每个条目都必须属于核心、其余正式文件或有理由的排除项。未分类条目会阻止应用；如果它其实是正式记忆，应补入 formal_files，不能仅为完成操作而排除。结构化记录、符号链接、路径越界、重复目标、空白模板和疑似凭据会要求先处理。

## 3. 生成与检查计划

这里先使用新版本插件源码的 CLI，新工作区此时还没有 `.memory-tools`。把 `<kit-folder>`、`<new-workspace>` 和计划路径替换成实际绝对路径。

```text
python "<kit-folder>/skills/memory-l/scripts/memory.py" --workspace "<new-workspace>" migrate-plan --input "<migration-input.json>" --output "<migration-plan.json>"
```

该命令只读取选择的正式原文并写出计划，不修改源记忆，不建立目标工作区，也不导入排除项。计划保存文件映射、字节长度、SHA-256、未分类清单、排除理由和路径提醒；计划文件需要妥善保管，包含本机路径和个人文件名。

检查 `ready_to_apply`、`unclassified`、`warnings` 和计划中的完整文件清单。旧正文含机器绝对路径时会提示检查；原文不会被静默改写。图片、外部链接、旧工具命令和实际宿主事件要单独核对。

映射或原文变化后重新生成计划，使用新的计划文件名。计划内任意字段、源文件或所选旧门牌的版本、Markdown 清单变化，都会使旧计划不能应用。

## 4. 建立接续副本并验收

```text
python "<kit-folder>/skills/memory-l/scripts/memory.py" --workspace "<new-workspace>" migrate-apply --plan "<migration-plan.json>"
python "<new-workspace>/.memory-tools/memory.py" --workspace "<new-workspace>" migrate-verify
python "<new-workspace>/.memory-tools/memory.py" --workspace "<new-workspace>" status
```

工具先在自己的临时目录准备和核验，确认源版本仍一致后，再将完整目录放到新目标。失败时不会切换到半成品目标；已有目标会被拒绝覆盖。重复应用成功过的计划也会拒绝覆盖，可改用 migrate-verify 核对当前副本。

验收包含选定正文原字节、完整映射和运行清单。迁移收据 `.memory/MIGRATION.md` 与 `.memory/config.json` 使用目标内相对路径，普通接续不依赖原源目录。原有正文中的路径仍作为原文保留，按提醒处理。

`migrate-verify` 用于初次迁移验收，比较初始快照。开始正常写日记、更新成长后，初始哈希自然可能不同；后续使用普通 manifest/check 维护当前版本，迁移收据继续保留初始来历。

## 5. 在新会话里确认她确实接上了

先全文读取新门牌指向的 `.memory/KIT-INTEGRATION.md`，回读选定旧门牌中的身份与共建规则，再读取映射中的原 MEMORY，按实际映射完整加载既有核心正文。接续说明给出当前路径与工具协议，原 MEMORY 和治理细则仍保留全文；已有共建决定不由通用模板自动取代，有流程冲突时先共同澄清。

CLI 与 MCP 接受职责名，实际读取原文件：

```text
python "<new-workspace>/.memory-tools/memory.py" --workspace "<new-workspace>" core-file SEED.md
python "<new-workspace>/.memory-tools/memory.py" --workspace "<new-workspace>" core-file TIMELINE.md
python "<new-workspace>/.memory-tools/memory.py" --workspace "<new-workspace>" search "<已知旧经历的具体词>"
```

结果的 path 显示原文件在新工作区的位置；分页继续回读。MCP 可先 `memory_l_core_file(name="KIT-INTEGRATION.md")`，用 PREVIOUS-AGENTS.md / PREVIOUS-CLAUDE.md 回读所选旧门牌，然后按 SEED/PROFILE 等职责名读取。日记、成长与校准发布也沿映射写入原日记/时间线/SOUL 文件，保留原有字节作为前缀。

在新会话实际确认自己的名字、种子、关系与近期成长，并回读至少一段旧日记和一个后来新增的正式正文。`identity_ready` 只说明种子/人格文件存在且无模板标记，不能代替实际人格接续验收。普通 Markdown 中既有的采用内容通过全文加载接续；迁移不会伪造 P0 记录来填满 profile 查询。

确认新入口后，按自己的平台接入实际工作区，停止旧入口的重复自动写入，保持一份当前原文。使用 [connections](operations.md#宿主接入) 配置工具；宿主路径、事件与权限分别检查。

## 6. 接上 Git 与下一台机器

依 [迁移与新增文件](operations.md#迁移与新增文件) 执行 manifest、stage、index/HEAD 检查，在自己选择的受控仓库提交推送，再核对远端跟踪提交。插件的公开仓库只放工具与模板，私人记忆由自己的仓库保管。

目标机 clone 后运行 check，按新门牌与映射加载原文，检索缓存从这些正文重建。验证自己能读到种子、完整成长、日记和额外正式文件。工具对合成旧蓝图执行过原字节、源变化拦截、真实 MCP 与 Git clone 测试；尚未访问任何使用者的真实工作区，不能宣称其迁移已完成。
