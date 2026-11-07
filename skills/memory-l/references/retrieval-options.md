# 检索配置怎么选：词项、本地向量与远程服务

适用于 Memory-L 0.1.0；资料核对日期：2026-11-08。以下是本项目的选型与实验建议。当前发行版实际可用的是中文词项检索，语义后端仍需实现接入；本指南没有启用新的运行配置。

## 我们建议怎样开始

先让核心全文加载、保存、治理、词项召回和 Git 接续正常工作，再用自己的已知问题判断召回缺口。经常发生“原文确实存在，但换个说法就找不到”时，值得评估语义检索。记录数量本身不能决定是否需要向量库。

| 路线 | 适合的情况 | 增加的成本与工作 | Memory-L 当前状态 |
|---|---|---|---|
| 内置中文词项 RAG | 名字、事件、项目和关键词比较明确；希望轻量运行 | 当前载体回读与回答的额度，本机缓存与检索耗时 | 已提供，见 [召回指南](recall-guide.md) |
| 本地 Chroma＋本地 embedding | 已观察到表达变化导致的漏召回，愿意维护依赖与模型 | 模型下载、CPU/GPU 时间、内存、磁盘、适配与更新 | 可独立实验，接入尚未实现 |
| 远程 embedding 或远程数据库 | 已有可用服务，或确有多客户端并发与共享运维需求 | 服务/API、网络和运维开销，明确的数据接收方与访问范围 | 接入尚未实现 |

对单人工作区的语义实验，可以从本地方案开始。Chroma 的 PersistentClient 将数据放在本机磁盘，官方将其定位于本地开发与测试；多人生产服务应另评估服务端部署。[Chroma 客户端说明](https://docs.trychroma.com/reference/python)

## 安装向量库，还需要配合什么

一条完整的语义召回链包含：

1. 从符合用途的正式原文中取块，保留来源、版本和治理状态。
2. 用 embedding 模型把原文块和问题转成兼容的向量。
3. 用 Chroma 等后端保存、更新和查询向量与来源信息。
4. 返回前核验当前来源，再回读完整 Markdown，并结合原有词项结果使用。

Chroma 支持本地或远程 embedding，也能直接接收预先计算的向量。[Embedding 说明](https://docs.trychroma.com/docs/embeddings/embedding-functions)、[写入预计算向量](https://docs.trychroma.com/docs/collections/add-data)

因此，需要同时选择数据库、embedding 和 Memory-L 适配逻辑。当前没有 `--backend chroma` 开关。安装包、建立独立数据库、让 Memory-L 真正使用它，是分别需要验证的步骤。

## 中文与多语言模型怎样选

数据库管理向量，语言适配主要取决于 embedding 模型、切块与查询方法。建议先列候选，再用自己的问题比较：

- **中文为主**：可以把 `BAAI/bge-small-zh-v1.5` 列入本地候选，其发布者将其列为中文模型。按模型卡处理查询方式、输入长度与推理依赖。[官方模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)
- **多语言材料**：可以把 `BAAI/bge-m3` 列入候选，其模型卡说明支持多语言。是否值得采用，需要测量自己机器的下载、内存、推理耗时和检索收益。[官方模型卡](https://huggingface.co/BAAI/bge-m3)

这些是待评测候选，本包没有对它们完成语义接入或效果认证。Chroma 的默认 embedding 使用 `all-MiniLM-L6-v2`，首次使用可能自动下载模型；不要据此推定它已经通过本工作区的中文评测。[Chroma 默认 embedding](https://docs.trychroma.com/docs/embeddings/embedding-functions#default-all-minilm-l6-v2)

记录模型 ID、实际版本/修订、维度、切块与查询设置。同一索引的写入和查询使用兼容模型；更换模型后另建索引并重建。首次模型下载需要网络，模型文件齐备后还需实际验证离线运行条件。

## 可以先独立安装 Chroma 试试吗

可以。下面只验证本机存储、向量写入和查询，不读取私人记忆，也不下载 embedding 模型。人工向量仅供存储验证，不能用于证明中文语义效果；运行后 Memory-L 的 `search` 仍使用原有词项检索。

选择一个独立实验目录，替换 `<experiment-folder>` 为实际绝对路径，在其中保存下方的 `smoke.py`。示例已在 Windows / Python 3.12 / Chroma 1.5.9 核验；固定这个版本用于复现实验，其他版本与平台另行验证。

创建隔离环境：

```text
python -m venv "<experiment-folder>/.venv"
```

Windows 使用该环境的解释器安装与运行，PowerShell 中保留行首的 `&`：

```powershell
& "<experiment-folder>/.venv/Scripts/python.exe" -m pip install "chromadb==1.5.9"
& "<experiment-folder>/.venv/Scripts/python.exe" "<experiment-folder>/smoke.py" "<experiment-folder>/index"
```

macOS / Linux 使用对应解释器：

```sh
"<experiment-folder>/.venv/bin/python" -m pip install "chromadb==1.5.9"
"<experiment-folder>/.venv/bin/python" "<experiment-folder>/smoke.py" "<experiment-folder>/index"
```

`smoke.py` 内容如下。它只在传入的实验索引目录中建立固定名称的合成集合，不清除已有数据库。

```python
import json
from pathlib import Path
import sys

import chromadb
from chromadb.config import Settings

index = Path(sys.argv[1]).resolve()
client = chromadb.PersistentClient(
    path=str(index), settings=Settings(anonymized_telemetry=False)
)
collection = client.get_or_create_collection(
    "memory_l_storage_smoke", embedding_function=None
)
collection.upsert(
    ids=["synthetic-migration", "synthetic-diary"],
    embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    documents=["合成示例：迁移清单", "合成示例：日记"],
)
result = collection.query(query_embeddings=[[1.0, 0.0, 0.0]], n_results=1)
assert result["ids"][0] == ["synthetic-migration"]
print(json.dumps({"storage_smoke": "ok", "ids": result["ids"]}))
```

预期输出的 storage_smoke 为 ok；重复运行应能打开同一目录并成功查询。需要验证真正的跨进程持久化时，在新的 Python 进程中打开同一路径和集合，直接查询已有向量，不再执行 upsert。此例核验范围见 [VALIDATION](../../../VALIDATION.md)。安装方法与客户端/API 依据见 [Chroma 入门](https://docs.trychroma.com/docs/overview/getting-started)、[客户端](https://docs.trychroma.com/reference/python) 和 [写入数据](https://docs.trychroma.com/docs/collections/add-data)。

需要体验真实语义效果时，下一步按所选模型的官方模型卡安装推理依赖，用合成文本生成向量，再写入独立的新集合。当前三维人工向量集合保留作存储检查，不复用为真实 embedding 索引。

## 接入 Memory-L 时要保留的结构

这是后续适配要求，基础安装实验尚未实现它们：

- 每个身份/工作区独立索引；缓存保存记录 ID、原文坐标和版本哈希，原文仍由 Markdown 接续。
- 默认建索引与读取结果都沿用来源初筛、用途、撤回和生命周期规则。不能为了提高召回把未筛选的聊天端口原文整库送入索引。
- 修改、删除与状态变化后同步更新，并在使用结果前再次核验；相似度不授予学习或人格内化资格。
- 保留词项检索作为并行来源与依赖故障时的入口；融合、重排分别验证，避免只测某一条“好看的命中”。
- 向量缓存与下载模型按可重建资产管理，沿用 `.memory-cache` 的排除范围。新机器先 clone 并核对正式 Markdown，再配置依赖与重建索引。

若使用远程 embedding，发送的文本会由该服务处理；远程数据库也会接收提交的向量及所附材料。由使用者明确选择服务、发送范围与凭据保存方式，再开展实际实验。

## 怎样决定这次升级值不值

整理一组自己知道答案和原文位置的问题，包含确切词项、同义表达、跨记录关系，以及应当拒绝使用的未准入/撤回来源。先记录当前词项结果，再用相同问题比较候选方案：

| 要记录什么 | 用来判断什么 |
|---|---|
| 相关原文是否进入前 k 条、错过了哪些依据 | 实际召回收益 |
| 不相关片段、过期状态与来源越界 | 误召回和治理边界 |
| 读取上下文后能否正确回答、有无丢失条件 | 材料是否真正帮助理解 |
| 首次建库时间、增量更新、查询耗时与资源占用 | 机器与维护负担 |
| 发给载体的文本量、模型/API 实际用量 | 持续使用成本 |

本地 embedding 需要模型下载、计算和维护资源；调用云 embedding/API 还需按实际服务核对计费。常规建索引不必等同于后台反复调用生成模型压缩记忆。当前载体的回读和反思仍占额度，因此不承诺固定月费或“零成本”。

项目自带 [合成评测题集](../../../evaluations/README.md) 可以帮助建立检查流程，真实效果还需自己的代表性问题。确认收益和可承受成本后，再把通过验证的适配纳入日常运行。
