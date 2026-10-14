# 髋膝正常核心流程：规则＋真实文本模型验收

日期：2026-10-14。适用本机已配置的模拟环境。业务决定见 [Q17—Q23 复核](./SETTLEMENT-SCOPE-REVIEW.md)。

## 1. 已完成的结果

已修改并发布原有的 **髋膝关节正常核心流程（数据库＋API）**，共 42 个 Business 节点。没有另建一个同名画布来代替原画布。

- [打开画布](http://localhost:3000/flow/e55b03b0-7c7f-420b-b720-33b1a4cf5559)
- 方案：`core.normal.1791804428546`，发布版本 **2**。
- [查看通过的任务](http://localhost:3000/business/tasks/34daafef-3b63-4b3f-8c2e-55d18bc7bee8)
- 任务由公开任务 API 提交，本地 `demo-regulator` 来源获准调用该方案，真实后台 Worker 执行。
- 执行状态 `completed`，覆盖核算状态 `accounted`；2 条结算明细，类别、数量、金额各 2 项一致，覆盖缺口 0。

| 样例 | 手术名称 HILIST_NAME | 耗材描述 PRODNAME | 就诊标记 | 分类方法 | 最终类别 | 数量／单价 | 比较结果 |
|---|---|---|---|---|---|---|---|
| MOCK-DETAIL-HIP | 人工全髋关节置换术 | 人工髋关节（模拟A型号） | 3 | 明确规则 | 人工髋关节 | 1套／10000元每套 | 类别、数量、金额一致 |
| MOCK-DETAIL-KNEE | 人工全膝关节置换术 | 膝关节假体系统（模拟成套产品B） | 1 | 真实文本模型 | 人工膝关节 | 1套／5000元每套 | 类别、数量、金额一致 |

膝关节样例的材料描述有意不直接命中“人工膝关节”字符串规则，确保验收确实经过模型分支；它与对应检查表的就诊标记同时设为 1，确认非住院记录不会被固定条件排除。CNT、PRIC 未被分类节点改写。

## 2. 固定筛选在哪里

`Settlements` 的 Connection 仍是模拟结算 PostgreSQL，Schema=`public`，Table=`core_flow_settlement_v1`。查询条件为：

| 源字段 | 条件 | 取值 |
|---|---|---|
| ORGAN_NAME | eq | 任务参数 hospital_name |
| UPDATE_TIME | ge / le | 任务参数 start / end，Asia/Shanghai |
| MED_PAY_FLAG | eq | 文本 `"1"` |
| LIST_TYPE | eq | 文本 `"301"` |
| REFD_SETL_FLAG | eq | 数值 `0` |

没有 `OP_EM_MARK=3` 条件。旧 `NormalPaid` 过滤节点已移除。`SettlementChecks` 保留数据质量及身份检查，数值条件为 CNT、PRIC 非负；没有就诊类型的固定值筛选。后续 `StudyChecks` 仍核对结算与检查的就诊类型是否一致，这与“只允许住院”不同。

统计范围是这个查询**实际返回的医保耗材非退费明细**。被查询条件排除的药品、其他期间记录等不作为本任务的结算源记录；检查、序列和影像源数量单独展示，不累加成结算明细数。

## 3. 分类节点及依据

`ClassificationSignals → NameRules → NeedsModel` 先检查具体耗材描述中的明确名称。当前规则覆盖“人工髋关节”“人工膝关节”，以及一个明确的模拟非关节对照名称。未命中意味着无法确定，不能当成其他耗材。

- 规则已确定：`RuleClassification` 保存类别、字段原文和规则理由；模型置信度为空。
- 规则无法确定：`NameModel → ModelResponses → ModelEvidence → ModelClassification`。
- `Classified` 合并两路；`ClassificationResults` 输出“耗材名称分类与依据”。
- `TargetNames` 让髋／膝继续；`Undetermined` 将无法确定记录保留为未比较，将明确其他耗材记录记为排除。

`NameModel` 配置：

| 配置 | 值 |
|---|---|
| Connection | SiliconFlow DeepSeek-V4-Flash（耗材分类） |
| Base URL / Path | https://api.siliconflow.cn / `/v1/chat/completions` |
| Mode / Model | openai / `deepseek-ai/DeepSeek-V4-Flash` |
| Input fields | HILIST_NAME、PRODNAME、HOS_PROJ_NAME、MEDINS_LIST_NAME、SPEC |
| Output fields | model_category、model_reason、model_evidence_field、model_evidence_text、model_confidence |
| Max calls | 本轮受控模拟为 10 条；未按生产批量设置 |

访问密钥仅保存在 Business 加密连接中，不在画布、脚本、提示词或验收文档中。发送给在线模型的是本轮合成的名称及规格信息，不包含姓名、证件号、数量或价格。

结果检查要求：类别明确、理由非空、引用单个已声明的耗材字段、引用原文确实存在、没有与已明确源信息冲突。只引用手术名称不够；凭空编造、空白或多个字段名拼接的依据不采用。置信度取值要求为 0—1，只用于显示，没有自动放行分数阈值。机械引用检查不能证明语义必然正确，样本预期结果另行验收。

在任务详情的 Dataset 下拉中选择“核心流程核验结果”查看最终比较，选择“耗材名称分类与依据”查看规则／模型理由；页面默认可能先展示原始记录去向核算表。

结果额外保存的字段是 `target_category`、`classification_method`、`classification_reason`、`classification_evidence_field`、`classification_evidence_text`、`classification_confidence`。这些是节点派生字段，不冒充数据库原列。

## 4. 数据库与影像链路

```text
Task Start → Settlements → SettlementChecks → 规则/模型分类 → UnitContext
Task Start → Studies（MySQL INSPECTION_INFO_RECORD）→ StudyIdentity
两路 → SettlementStudies（医院＋系统＋RPT_NO）→ StudyContext
     → CheckTime → StudyChecks → StudyBodyPart → JointStudies
Task Start → Series（MySQL SERIES_INFO）→ SeriesIdentity
两路 → StudySeries（医院＋系统＋ris_study_id）→ SeriesContext → SeriesChecks
     → Images API（series_id = global_id）→ ImageContext（domain + file_path）
     → ImageChecks → Manifests（每条耗材的影像清单）
UnitContext + Manifests → UnitEvidence → ObservationInput → EvidenceChecks
     → Observation → ObservationChecks → Amounts → CompareQuantityFee
     → ResultFields → Results
```

- `Studies` 使用监管提交的同一起止时间查询 `chk_dt`，不再计算结算前 7 天。`chk_dt` 仍为真实记录值。
- 本地 MySQL DATETIME 按北京时间解释，转换后与结算时间比较；保留检查时间早于结算时间的条件。
- 检查和结算的就诊标记先统一为文本再比较，避免 INT 与 TEXT 的类型差异。
- 两张 MySQL 表的 `link_id` 按既定 MD5 规则生成；`study_primary_id=link_id`，`series_id=global_id`。
- 不将未知码值含义的 `upload_status` 冒充旧 API 的 `is_upload`。
- `unit_row_id` 在关联展开前生成，影像清单汇总后回连原始耗材单位；不因一条耗材有两张影像而把数量或金额重复计算。

本轮序列表是已知有限的两条模拟记录，先读全表再按医院、系统及检查关联。大规模生产序列读取的下推优化不在本轮验收范围。

## 5. 验收证据与问题修正

[完整验收摘要](./evidence/core-classification-20261014/acceptance.json)记录：结算 2 条、检查 2 条、序列 2 条、影像 4 条、耗材影像清单 2 份、独立影像模拟观察 2 条、真实文本模型调用 1 次。没有再调用检查列表或序列列表 API。

[分类结果](./evidence/core-classification-20261014/classification-rows.json)中，膝关节模型结果引用 PRODNAME 原文，置信度为此次返回的 0.95；这不表示已验证 95% 正确率。[最终结果](./evidence/core-classification-20261014/result-rows.json)保留源数量、源单价、独立观察数量、折算金额及差值。

[真实模型局部边界测试](./evidence/core-classification-20261014/model-boundaries.json)另验证：

1. 同一髋关节手术下的“医用骨水泥（模拟辅助材料）”判为其他，没有仅凭手术名称归成关节假体。
2. “模拟材料，未提供具体名称”判为无法确定，没有强行分类。

实施中修正：

- 首次连通测试返回合并字段名，不能逐字段核对。改为单字段引用提示，并增加运行时检查。
- 规则对“明确其他耗材”与髋／膝描述共存的冲突原先处理不足。增加冲突信号，禁止自动通过，并补测试。
- 第一次完整任务的 `REFD_SETL_FLAG` 被写成文本常量，PostgreSQL 报 `numeric = character varying`。改为数值 0，并在发布脚本中增加真实只读查询预检。[复现与修正证据](./evidence/core-classification-20261014/numeric-filter-regression.json)。失败任务仍保留，未删除或改写历史。
- 原方案的 allowed_sources 为空，模拟监管端无法提交。只为该自有核心方案加入本地已配置的 demo-regulator；其他方案权限保持原样。

后端变化仅扩展受限表达式支持条件表达式、比较、布尔逻辑及 contains，用于普通 Transform 的规则和依据检查。没有开放 Python 执行、属性访问、下标访问或任意函数调用，没有把本业务判断写死进通用 Database。

最终完整业务回归 **100 项通过**，包括实际 MySQL／PostgreSQL 测试；新分类与受限表达式边界测试 21 项包含其中。6 条警告来自现有依赖的弃用提示，无测试失败。

[浏览器验收](./evidence/core-classification-20261014/browser-report.json)已通过：NameModel、Studies、Series 配置可打开且无表单错误；Task Start 可选中已完成任务并显示真实接收参数；任务详情可选择最终结果数据集。没有页面脚本错误，浏览器查看没有改写保存画布。截图：[任务入参](./evidence/core-classification-20261014/canvas.png)、[任务结果](./evidence/core-classification-20261014/task-results.png)。

## 6. 重现与边界

在项目根目录启动全部已配置服务：

```bash
bash scripts/business/start_local.sh
# 需要重启服务时：
bash scripts/business/start_local.sh --restart
```

检查当前画布配置并实际预览三张源表，不修改画布：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python -m scripts.business.apply_core_classification
```

提交新的模拟任务并验收（会调用付费文本模型一次）：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python -m scripts.business.verify_core_classification
```

只复查已完成任务、不再次调用模型：在上条命令末尾增加 `--task 34daafef-3b63-4b3f-8c2e-55d18bc7bee8`。

受控更新画布的脚本为 `apply_core_classification --apply`：先通过 `maintenance_local.py close --wait 60` 暂停新任务并等已接任务结束，应用后用 `maintenance_local.py open` 恢复。该脚本仅适用于本机现有连接和两条指定 MOCK 数据；旧画布及源记录备份在 `deploy/verification/.cache/core-classification-20261014/`。升级运行时代码时应先按启动脚本停启服务，再重新发布兼容版本。

**本轮已经打通的是模拟结算／检查／序列数据＋模拟影像列表和影像识别＋真实在线文本分类的正常核心路径。** 影像地址仍是模拟地址，没有调用真实影像模型，也没有证明生产数据上的分类准确率。退费、异常处理、人工复核、生产吞吐与置信度校准不在此次验收范围。
