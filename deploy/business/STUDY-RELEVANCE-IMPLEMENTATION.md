# 检查编码与 11 节点核心流程实施记录

日期：2026-10-14。依据：Q34—Q38 以及用户要求修改代码、数据库和实际画布。验收结果以本文末尾的运行记录为准。

## 实际改动

1. 本地 MySQL `business_demo.INSPECTION_INFO_RECORD` 增加 `EXAM_PART VARCHAR(128)`，现在 95 列。`ckpt_code` 保留原含义，没有复制成新标准码。序列表仍为 164 列，结算表仍为 51 列。
2. Studies 返回原始 `EXAM_PART → study_exam_part`，以及 `chk_desc → study_chk_desc`、`proj_name → study_proj_name`；Studies、Series 均允许 DR、CT。删除 Lookup 的 Category match 配置和执行分支。
3. 新增画布实例 StudyRelevance，复用 Business Classification。它先解释标准码，再判断检查与本条 `target_category` 的相关性。主画布为 9 种类型、11 个实例；左栏没有新增髋膝专用类型或独立字典节点。
4. Classification 支持结果前缀、可选标准字典和规则前置等值条件。第一轮仍输出 `target_category`、`classification_*`；第二轮输出 `study_relevance`、`study_relevance_*`，不会覆盖原分类、CNT 或 PRIC。
5. Images 继续按原耗材身份收集地址，额外保存 `image_manifest_context`：每个地址对应的检查、序列、实际模态、原码、标准名称、版本、出处和判断依据。Observation 实际收到该字段，并检查它与受控影像清单的一致性。
6. 检查级 Issues 保存但不必连线。结果核算增加后备原因：只有原明细没有实际比较结果时才使用检查不适用的原因；若有另一检查完成核验，则不会因某个检查被排除而把整条耗材判成已排除。

最终连线：

```text
Task Start → Settlements → SettlementChecks.Valid → Classification
  → Studies → StudyRelevance.Data → Series → Images → Observation
  → Compare → Results
```

## 字典与界面

字典 ID 为 `wst364.8-2023-cv04.30.002`。依据用户提供的 PDF 表 2，保留原码、原文、PDF 页序、印刷页码、文件 SHA-256 和标准来源 URL。481 个来源条目归并为 479 个代码：464 个可精确解释、13 个源码格式疑点、2 个同码多义。疑点条目没有被自动修正。

未知、空值、源码格式疑点和同码多义分别保留状态；这类记录不发送给模型猜码。字典内容纳入执行版本指纹，改码表需要重新发布。

StudyRelevance 的“结果命名与标准字典”区域提供结果前缀、字典选择和上游编码字段。标准名称等派生字段自动加入分类字段下拉，来自字典输出结构，不是假称数据库已经有这些列。标准名称作为证据，`target_category` 作为本条目标上下文；每条规则可展开配置前置等值条件。

中文、英文文案已添加；其他现有语言的新键暂使用英文。完整系统指令仍可展开查看，随字段、类别、字典、规则和业务说明生成。

## 受控样例

2 条结算明细分别保持 1 套，髋单价 10,000 元、膝单价 5,000 元。它们关联 5 个检查、5 个序列，共 12 个模拟影像地址。

| 原明细 | 检查代码 | 实际模态 | 标准含义 | 判断路径 |
|---|---|---|---|---|
| HIP | BQ02ZZZ00 | DR | 双侧髋关节前后位 | 规则 |
| HIP | BQ20ZUZZZ | CT | 右侧髋关节 CT 薄层扫描（3D VR 处理） | 规则 |
| KNEE | BQ07ZZZ00 | DR | 右侧膝关节前后位 | 规则 |
| KNEE | BQ27ZUZZZ | CT | 右侧膝关节 CT 薄层扫描（3D VR 处理） | 规则 |
| HIP | BQ03ZZ900 | DR | 右侧股骨前后位（近髋） | 在线模型结合原始检查描述 |

第五条的受控检查描述明确写明采集范围包含髋关节；模型判断的是候选相关性。该描述并非标准名称本身，也不代表真实影像已经确认覆盖。规则按当前目标判断，因此膝关节检查不会因为属于某种关节就自动成为髋关节候选。

第一轮耗材分类仍是髋样例走规则、膝样例因未命中明确规则而调用模型；第二轮是 4 条明确检查走规则、1 条宽泛检查走模型。不是按髋／膝类别固定选择模型。

## 回归边界

定向测试覆盖：原始代码精确解释；同码多义和未知码不调用模型；第二轮保留第一轮分类；目标不同导致检查去向不同；明确 CT／MRI 技术与 DR 等源模态冲突不能作为规则确定结果；多检查影像上下文保留且金额不倍增；无适用检查的原明细有原因，已有结果的原明细不受另一条检查排除影响。

另外将过时的“检查 API → 序列 API”核心模拟测试更新为当前数据库来源身份＋影像 API 的样例，覆盖 DR、CT、完整地址集合、错误编码上下文和独立观察数量；没有通过放宽识别断言掩盖旧样例与当前业务口径的差异。

本轮不扩展完整侧别核验，也没有真实医学影像识别验收。标准名称中的左右侧原样保留；耗材侧别未知时不据此猜测。后续若增加明确的耗材侧别字段，应在规则／冲突条件中绑定真实字段，不能仅凭模型提示词宣称已经核对侧别。

## 运行与复验

第 4 版已启用，新任务 `dea219d9-72f6-46b9-a76b-df49d8574d46` 已完成全部 11 节点。升级前的画布与本地模拟记录备份在 `deploy/verification/.cache/study-relevance-20261014/`。备份用于核对，执行器没有新增已舍弃 Category match 的兼容分支。

完整启动命令：

```bash
bash scripts/business/start_local.sh
```

完整重启命令：

```bash
bash scripts/business/start_local.sh --restart
```

复验脚本 `scripts/business/verify_compact_core.py` 使用当前 11 节点契约；传入 `--task` 时只读取已有任务，不再调用在线模型。数据库元数据及联查验收由 `scripts/business/prepare_core_database_sources.py --apply` 执行，仅读写本地、明确归属本项目的模拟记录。


## 实际任务结果

- [当前 11 节点画布](http://localhost:3000/flow/ce588a72-0614-4d84-badd-0e4355c427e6)
- [已完成任务](http://localhost:3000/business/tasks/dea219d9-72f6-46b9-a76b-df49d8574d46)
- 发布：`core.normal.compact.v1` 第 4 版，发布 ID `0dad5d43-06e7-471d-9be3-c5d42c05f7f3`。

真实 Worker 运行时：结算／有效明细／耗材分类均为 2 行，检查关联／检查适用性／序列关联均为 5 行，影像清单／观察／比较／最终结果均回到 2 行。髋明细对应 7 个地址，膝明细对应 5 个地址；两者识别数量仍为 1 套，计算金额分别 10,000 元、5,000 元，类别、数量、金额合计 6 项核验全部一致。原明细覆盖缺口为 0。

真实在线文本模型共调用 2 次：耗材分类 1 次、检查适用性 1 次。后者引用检查描述原文“采集范围包含髋关节”，判为候选相关；自报置信度 0.9 仅展示。模拟影像观察调用 2 次；本次仍没有真实医学影像识别验收。

配置、标准解释和原始字段保存在节点数据集；最终表保持原业务展示列，完整逐影像来源在 Images 数据集中查看，不把所有技术字段铺入最终业务表。

检查结果：业务回归 **147 项通过**（显式启用真实 MySQL／PostgreSQL，无该类跳过）；模拟影像服务 **11 项通过**；前端 Business 配置 **7 组、24 项通过**；全量 TypeScript 及最终增量检查通过；改动文件 Ruff／Biome 检查通过。

证据：[验收汇总](evidence/study-relevance-20261014/acceptance.json)、[发布状态](evidence/study-relevance-20261014/deployment.json)、[检查判断](evidence/study-relevance-20261014/study-relevance-rows.json)、[逐影像来源](evidence/study-relevance-20261014/image-manifest-rows.json)、[最终结果](evidence/study-relevance-20261014/result-rows.json)、[后端日志](evidence/study-relevance-20261014/backend-tests.txt)、[前端日志](evidence/study-relevance-20261014/frontend-tests.txt)。

复查本次任务（不再次调用模型）：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python -m scripts.business.verify_compact_core \
  --task dea219d9-72f6-46b9-a76b-df49d8574d46
```


浏览器端到端验收 **1 项通过**：实际打开 11 个节点；核对 StudyRelevance 字典、独立结果前缀、派生字段、四条目标条件规则；核对 Studies 中 EXAM_PART 真实下拉和 Category match 已移除；检查序列字段、影像清单与任务最终两条结果。

[浏览器日志](evidence/study-relevance-20261014/browser-tests.txt) · [检查适用性配置截图](evidence/study-relevance-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/study-relevance.png) · [任务页截图](evidence/study-relevance-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/compact-results.png)。

服务已在宿主环境通过项目启动脚本持久运行。已确认启动脚本退出后六个 tmux 服务仍存在，平台健康检查返回 200，并在此状态完成上述真实 Worker 和浏览器验收。
