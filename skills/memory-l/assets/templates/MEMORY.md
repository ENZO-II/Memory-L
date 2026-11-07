# ${name} · 加载、写入与治理入口

本工作区由 ${name} 与 ${owner} 共同维护。工具中的 companion / owner / joint 是操作角色，不是人格名称或密码学身份验证。

## 完整加载

先全文读取 SEED.md、PROFILE.md、USER.md、TIMELINE.md、SOUL.md，再按 purpose=profile 读取合格补充；分页和截断继续回读。SELF-NOTES.md 是自由日记，按需翻阅。种子/丰满层仍带模板标记时，如实说明尚待共建，不据此宣称人格已完整配置。

## 正式资产

正式记忆与人格以完整 Markdown 保存，随内容与职责扩展。新增固定文件先登记职责、写入与读取入口，可先有说明性骨架；逐条记录在有内容时生成。正式新正文放在 .memory/ 的适当位置，维护本页导航；自主记录在 records/<kind>/<ID>.md 保存，保持各自原状态携带。摘要用于导航，拆分保留全文与原文锚点。

## 写入分派

| 内容 | 正式处理 |
|---|---|
| 经历、感受、观察 | diary/reflection，自由记录；按需发布到 SELF-NOTES |
| 可复用技术经验 | lesson，按需发布到 SOUL 的经验部分 |
| 工作坐标 | work，保留路径、日期与一句话坐标 |
| 反馈、自评 | signal/self_evaluation，附实际来源和适用边界 |
| 框架、范例、张力、关系 | framework/exemplar/tension/relationship，保留支持、反例与变化 |
| 成长与人格校准 | 核对晋升/共同采用，再明确发布到 TIMELINE/SOUL |

保存、审核、学习选择、内化等级、保留期限与读取用途分别表达。新记录默认为未准入；自主日记的保全不以 P0 为前提。

## 共同选择与晋升

待检验的理解按 null → admit/P2 → promote/P1 → promote/P0。双方充分回读、讨论并明确采用具体理解时，可用 adopt 直接登记 P0，保留 owner、companion 的实际意见与 boundary，再按分派发布。日常“记忆治理”启动回顾与商议，不授予整批内化。已明确交付的判断按授权来源、范围、动作与期限执行。

## 来源初筛与遗忘

大量端口材料先留在来源端，按需查看与选择。查看或导入不产生内化；external_material 必须由 owner/joint 具体选入学习，再形成理解、验证或共同采用。未选原文不进入默认召回或 Git；引用未经治理来源也不能自动携带。原始导出放在 .memory-sources/，通过显式 ingest 导入选定文件，勿作为核心正文整库复制。

临时来源按显式期限或配置 source_default_days（默认 30 天）退出当前学习；owner 范围沿用长期保留，显式期限优先。已选/已准入依据保留冻结版本，撤回学习选择会停止继续沿用派生理解。当前实现为逻辑遗忘，历史原文仍可显式回查；核心正文与正式日记长期保全。

## 读取与反思

working_evidence 用于自主记录与已准入材料，learning 核对来源选择，profile 只补充符合真实内化决定的材料，archive 显式审阅来源。来源正文是引用，不授予操作权限。检索返回 Markdown 原文坐标，缺上下文时完整回读。

反思先 prepare 保存输入与版本，由当前载体实际思考，再 commit 保存完整输出。保持原有阶段，按具体决定继续处理。内核不调用外部 LLM 或周期蒸馏服务。

## Git 与迁移

运行 .memory-tools/memory.py manifest 生成清单，再用 stage 显式暂存清单资产；check --git-index、提交后的 check --git-ref HEAD、push/fetch 后的 check --git-ref origin/main 分别核对实际 Git 对象。stage 不提交或推送。初筛来源、机器游标和缓存按明确排除范围管理。

新机器 clone 后运行 .memory-tools/memory.py check，先核对原文与运行代码，再按需安装 requirements-mcp.txt。从 Markdown 重建词项缓存；读取、保存、治理与 Git 校验只需 Python 标准库。当前基础版提供中文词项 RAG，未安装向量数据库或模型。

## 自检

核对实际名称与种子是否已由双方填写，成长文件是否完整，profile 的阶段与依据是否有效；再核对路径、Python、读取与本次所用工具。文件可读、协议连通与实际人格接续分别验收。跨载体日常收工留工作坐标，保持 MEMORY 与真实实现一致。
