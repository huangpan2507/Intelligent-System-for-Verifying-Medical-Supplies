# Results 配置、业务展示与结果留存梳理

日期：2026-10-15。范围：髋膝关节正常核心流程（数据库＋API，精简11节点）的 Results。

状态：Q52—Q56 已实施代码、数据库结构和运行画布变更，核心方案发布为 v10。后续按用户反馈移除只有提示文字的独立“来源与证据”分组，当前为三组布局；每条实际结果内的“来源与证据”保留。此调整仅涉及前端展示，不改变模板、流程发布版本、结果保存和追溯关系。前半部分“改造前实现事实”及原四组设计保留作为历史背景。

来源记录、检查/序列/影像分层、识别调用弹窗及保存信息精简见 [Results 证据展示设计](./RESULTS-EVIDENCE-UX-REVIEW.md)；Q57—Q59 已实施，运行画布和中文任务结果页的只读验收已通过。查看前后原有2条结果、38条证据内容以及任务、识别调用数量均保持不变。

## 用户已经明确的要求

- 减少用户配置负担，不要求使用者理解后端对象结构或逐个维护大量字段。
- 最终结果必须保存必要字段，能够查回源明细、相关检查和识别依据；结果追溯不可省略。
- 希望通过预置中文模板展示患者、医院、结算项目、结算与识别数量、折算金额、差异及医院/系统/申请单标识。
- 表单按业务逻辑分组，采用紧凑编辑、折叠摘要和宽编辑；区分默认展示、按需查看和仅供系统留存的内容。
- 本轮讨论不改变11节点及已确认的类别、数量数值、数量乘单价的比较口径，不引入容差、单位换算或新的模型判断。

## 改造前实现事实（v9）

### 配置和执行

Results 是 Business Output 的实例。Output 契约包含 name、columns、key_fields、reason_fields、evidence_fields、primary、obligation。

| 配置 | 当前实现 | 简化时必须注意 |
| --- | --- | --- |
| name | 数据集名称，当前为“核心流程核验结果” | 不等于数据库表名 |
| columns | 从上游Compare的84列中选38列，额外保留_business_row_id，最终39列 | 省略/空列表会返回全部上游84列；不是自动保留“刚好必要”的字段 |
| primary | 多个Output时优先排列；当前覆盖契约还要求声明于primary Output | 单一Results无需人工选择；不能只删值却不调整发布检查 |
| obligation | 声明来源范围、明细身份、核验对象、事项结论及其他去向 | 与逐行来源追溯不同；取消后覆盖核算会降为ordinary/not_required |
| 顶层key_fields/reason_fields/evidence_fields | 字段存在性会校验，但无独立执行消费；当前均未填写 | 删除它们不会删除已实现的去重、追溯和证据记录；不能混删obligation内确实生效的单数reason_field/evidence_field |

来源追溯由父数据集及逐行lineage实现，Output选列后仍保留；覆盖核算由coverage.finalize/audit在任务收尾执行。obligation并不要求列出每个节点每个输出口的所有字段去向。当前只声明：Settlements读取范围、SettlementChecks身份、Classification目标对象、Compare三项状态及有明确意义的其他去向。

### 真实存储位置

当前本地平台 PostgreSQL 为127.0.0.1:55433，数据库verification，实际Schema为verification_scope。ORM中的逻辑Schema verification经schema_translate_map映射，不能误报为实际部署Schema。

| 实际表 | 内容 |
| --- | --- |
| verification_scope.business_task | 任务、方案/版本引用、请求条件、执行状态及结果数据集ID列表 |
| verification_scope.business_task_input | 监管端任务编号与规则名 |
| verification_scope.business_dataset | 数据集ID、所属任务/节点/端口、字段结构、行数、原始标记、父数据集与行溯源引用 |
| verification_scope.business_external_request | 识别及其他外部请求的输入关联、请求/响应、调用状态 |
| verification_scope.business_task_assessment | 核验覆盖与来源取齐情况的汇总 |
| verification_scope.business_release | 发布版本和当时的配置快照 |

不存在business_result逐条结果表。39列业务结果行目前写入deploy/verification/.cache/business-data/<task_id>/<dataset_id>.parquet；BUSINESS_DATA_DIR可改变根目录。business_dataset.fields是列结构，不是业务行；business_task.results是数据集UUID数组，不是39列数据。

当前核心v9验收任务0a0f4dbf-66a8-416d-9afe-4a6af6dc47c3：Results为39列、2行；task.results包含最终结果、三项核验明细和去向明细共5个数据集引用。识别请求/原始响应已经在PostgreSQL请求表保存，不等于最终业务结果已经逐条落库。

### 中文展示和追溯缺口

- 当前任务页主要按字段遍历表格，没有按正常/差异/未完成生成中文业务说明。
- 最终39列已有RPT_NO、ORGAN_CODE、SYSTEM_ID，以及患者/就诊、结算项目、类别数量金额和逐项状态。
- Compare中有image_manifest_context、_request_id、_identity、_comparison_status、recognition_confirmed、coverage_confirmed、_model_response，当前Results未选入。
- image_manifest_context保存逐影像的申请单、ris_study_id、link_id、series_id、模态、标准部位及相关性判断依据；影像地址列表不包含完整的这些来源信息。
- evidence_ref是服务提供的证据引用，不等于平台外部调用主键。新留存契约应保留_request_id或明确的请求关联，不得把evidence_ref冒充请求表主键。
- 当前_comparison_status在存在unknown时可能优先总体unknown；中文说明应读逐项状态，保留“已确认差异＋另有事项未完成”，不能只取一个总体字符串。

## 已确认决策

### Q52：内部配置由系统管理，删除无执行作用的入口

用户同意：“系统管理，删除无效配置”。

- 当前核验业务模板预设结果交代约定，平台依据明确的节点能力和绑定生成/校验内部契约；用户看到范围和三项检查摘要，不再手填嵌套obligation。
- 不声称能够仅凭任意画布连线推断所有业务义务。换来源、删节点或改分支后无法确定关系时明确报错，不静默关闭覆盖核算。
- 单个Results自动作为主结果，取消日常Primary开关。多个输出的主结果由流程结果设置或模板管理，不随机选择。
- 删除当前没有独立执行作用的顶层Key fields、Reason fields、Evidence fields；保留实际追溯链和覆盖内的原因/证据关系。

### Q53：确定性中文模板，不引入新大模型

用户同意：“模板展示，按实际状态组织”。

- 预置正常、存在差异、未完成三种结果表述，按三项状态填值；模板不能重新判断或修改源数据。
- 正常必须要求应比较事项均可用且一致。存在已确认差异时，逐项列明类别/数量/金额中的实际差异；若另有未完成事项，同时说明。
- 只有类别不同且数量金额一致时，不能输出“数量及金额差异”。没有得到有效结果也不能默认正常；明确排除的非目标记录不误报异常。
- 不扩展新的异常处理分支，只准确表述现有状态。当前模拟标记直接展示，不伪装真实影像识别。
- 差值继续为识别侧减结算侧，金额来自既有数量乘单价公式。展示可去掉无意义末尾零，但不舍入改变数值，不隐藏差异。
- 说明文字和模板版本应与当时结构化结果一起留存；不能修改模板后悄悄改写旧任务的结论文字。

### Q54：展示与留存分开，补齐最终结果落库

用户同意：“分开展示与保存，结果落平台库”。在现有平台PostgreSQL中新增逐条结果和证据关联的持久化，不写回模拟医院源库，也不要求业务人员配置Connection/Schema/Table。

- 日常不再手选或排序38项Columns。业务模板负责展示顺序和必须留存的字段，来源有效性由平台校验。
- 隐藏某字段或折叠证据不影响留存。不是直接删columns后将84列全部铺在页面上，也不是将现有39列照搬就宣称追溯完整。
- 结果至少保留任务/监管编号与发布版本关系、源明细身份、患者/就诊/医院/系统/申请单、结算项目与耗材描述、两侧类别数量金额、逐项状态与差值、分类依据、模拟标记及中文说明/模板版本。
- 通过明确关联保存检查/序列/影像来源、适用性依据、识别请求和原始响应、数据集与源行引用。保留现有原始数据集及请求记录；不要求在每条结果中重复复制全部原始响应或影像二进制。
- 物理列、结构化业务载荷及关联表按下述留存契约落实，保证通用Output能力不被髋膝字段写死。最终39列不应成为固定的存储上限。

## 结果留存与展示契约

以下是Q52—Q54对应的实现约束，不增加需要用户选择的技术配置；物理索引、外键和事务安排由实现负责。

### 结果对象与状态

- 保持本流程已有粒度：一条进入关节核验的耗材明细对应一个核验对象；不按患者合并，不因多次检查或多个序列生成多份数量/金额结论。通用平台继续使用各业务模板声明的核验单元。
- 对目标对象保存逐项状态与结论。已明确排除的非目标记录继续有独立处理去向，不伪装成正常或异常的关节核验结果。来源范围仍为Settlements实际读回的记录，不声称覆盖被数据库查询条件排除的记录。
- 结果说明读取类别、数量、金额各自状态。存在已确认差异时保留差异；其他事项未完成时同时提示。只有所要求事项均完成且一致，才显示本条核验正常。
- 单条结果正常与整个任务完成、结果交代完整是不同状态。显示某条正常时，不隐藏任务中其他对象的未完成或覆盖缺口。
- 既有未比较原因继续被记录；不因此新增异常处理业务分支。当前模拟识别标记明确保留。

### 平台数据库写入

- 拟新增verification_scope.business_result，逐条保存结果ID、任务/发布版本、输出节点/业务模板标识、核验对象关联、总体展示状态和完成情况、逐项结构化结果、中文说明及模板版本、原结果数据集与行引用。
- 业务事实以有明确类型和契约的结构化载荷保存；通用字段用于任务、对象、状态等检索，不在通用表中强制所有业务具有PSN_NAME、RPT_NO等髋膝专属物理列。
- 拟新增verification_scope.business_result_evidence，关联结果与其检查/序列/影像来源、原始数据集/行、识别调用记录及证据引用。保留关联范围；同一影像可以服务多个明细，不能跨明细删除关系。
- 现有business_external_request继续保存调用请求/响应；business_dataset及Parquet继续保存原始/中间记录及行溯源。新结果的核心事实和逐影像来源需在数据库有结构化保存或可靠表关联，不能只保存一段中文文字或一个文件路径就称为结果落库。
- evidence_ref与平台请求ID分开保存；RPT_NO与医院/系统共同使用，定位具体检查时继续使用ris_study_id/link_id；不以图片地址代替全部业务身份。
- 同一结果重复保存应幂等；保存阶段不触发再次识别或在线模型调用。新版本任务只有在必要结果与证据关联成功保存后，才能报告结果保存完成；保存失败不能展示成功或将缺失值填为正常。
- 不回写医院模拟源库，不改写既有任务的原始记录，不将旧任务冒充采用新模板生成的结果。通过新发布版本及新任务验收。

### 髋膝模板必须留存的业务内容

| 内容 | 当前字段或来源 | 保存与展示要求 |
| --- | --- | --- |
| 患者、医院、就诊 | PSN_NO、PSN_NAME、CERTNO、ORGAN_CODE、ORGAN_NAME、OP_EM_NO、OP_EM_MARK、SYSTEM_ID | 常用业务身份直接展示，其余按需查看；不因隐藏而删除 |
| 原始明细与结算事实 | SETL_FEE_LIST_ID、DATA_SOURCE、HILIST_NAME、PRODNAME、HOS_PROJ_NAME、MEDINS_LIST_NAME、SPEC、UPDATE_TIME、CNT、PRIC及明细身份 | 保存当时使用的事实；不把原始字段解释为模型输出 |
| 分类结论及依据 | target_category、classification_* | 结论进入比较，判断方法、原文依据及模型自报置信度按需查看 |
| 识别结果与确认情况 | recognized_category、recognized_quantity、recognition_confirmed、coverage_confirmed、simulated及原始响应关联 | 双方类别/数量直接展示；确认依据和原始响应可追溯 |
| 金额及比较 | settled_amount、observed_amount、category_status、quantity_status、amount_status、difference_1、difference_2 | 按既有公式和严格数值比较保存；不引入容差或舍入 |
| 检查与影像 | RPT_NO、image_manifest、image_manifest_context | 保存逐影像的检查、序列、标准部位及适用性依据；摘要与明细分层展示 |
| 调用与源行追溯 | _request_id、evidence_ref、_identity、unit_row_id、任务/数据集/行及发布版本关系 | 通过明确记录或关联留存；内部标识按需查看，不能要求使用者手工补齐 |

模板绑定从当前真实输出契约预设并校验。更换来源时，缺失必须字段要定位到具体业务用途；不能猜一个同名字段替代，也不能强制用户重新逐项选择全部字段。

## 已确认的界面与模板范围

### Q55：四组布局及统一预览

用户同意：“四组布局，节点与结果页统一展示”。采用下表四组；节点预览与任务结果页使用相同展示规则。节点可选择已完成任务查看真实结果；无任务时明确标为示例，不因打开配置而执行流程或调用模型。

| 分组 | 默认呈现 | 展开/宽编辑 |
| --- | --- | --- |
| 结果模板 | 当前业务模板、正常/差异/未完成的表述摘要 | 只读模板文字与字段说明；字段绑定由模板预设，失效时明确提示 |
| 结果预览 | 患者、医院、项目、结论及三项紧凑比较 | 选择已完成任务查看真实结果；无任务时标明示例，不以编排动作触发识别调用 |
| 来源与证据 | 申请单号、医院/系统、检查/序列/影像数量 | 逐检查/序列/影像来源、识别依据；内部ID在只读技术详情 |
| 保存与完整性 | 已保存状态、版本、核验范围及缺失提示 | 必需留存项清单和系统生成的覆盖关系；不要求逐项编辑数据库字段 |

日常业务页面不展开所有底层响应、内部主键、lineage映射；它们应被保存且可按需追溯。任务结果页与节点预览使用相同展示规则。模板示例和已发布任务的实际结果必须明确区分，历史任务预览按该任务保存的结果及模板版本读取，不以当前草稿重新生成结论文字。

### Q56：本轮只提供预置模板，不建设自由编辑器

用户同意：“本轮预置模板，不开放编辑”。先提供髋膝业务模板，使用者无需编辑文字占位符、字段映射和判断条件；正常/差异/未完成的说明按既有结果自动生成。模板随发布版本固定，历史结果保留当时文字。其他业务后续增加各自的模板，不把髋膝名称与字段写死在通用渲染器中。

本轮不建设自由模板编辑器，不新增模板编辑权限系统。未来若有自定义文字需求，再单独确定可编辑内容与结论约束；不将该可能需求作为本轮完成条件。

## 实施顺序

| 步骤 | 实施内容 | 通过标准 |
| --- | --- | --- |
| 1. 结果契约与中文模板 | 将业务展示、必需保存字段及系统管理的覆盖关系分别定义；提供髋膝预设，删除无执行作用的顶层配置 | 字段绑定来自真实上游；必需关系失效有明确错误；文案根据逐项状态生成 |
| 2. 数据库与保存流程 | 建立结果/证据关联存储，保留任务、版本、源行及调用关系；接入任务收尾保存 | 新任务必要结果真正写入PostgreSQL，保存幂等，失败不报成功 |
| 3. 查询与统一展示 | 提供按任务读取已保存结果及证据的能力；Results四组界面与任务页复用业务结果展示 | 查看不触发执行；默认只显示业务重点；证据/技术信息可展开，支持宽查看 |
| 4. 运行画布与发布 | 更新核心Results所用预设和内部配置，保存快照并发布；恢复项目服务 | 核心仍11节点，Compare→Results连线不变；比较公式和口径不变 |
| 5. 分层验收 | 相关后端/前端回归、数据库持久化验证、浏览器验证及真实Worker核心任务 | 两条核心模拟样例可查中文结果、结构化值和完整证据关联；报告验证范围及模拟边界 |

原始事实、最终结构化结果和保存的中文说明必须一致。平台通用能力、髋膝模板和画布实例分别维护，不用新增只能处理该业务的节点，也不将全部内部参数重新暴露在表单中。

## 验收范围

- 现有11节点核心链路保持；Results不再要求配置已确认移除/系统管理的项目，字段绑定仍通过真实结构检查。
- 检查正常、仅类别不同、数量及金额不同、未完成、差异与未完成并存的模板文字；输出事实和差值准确，显示不会改变数值。
- 检查结果表及证据关联真正写入PostgreSQL：由结果查到任务/版本、源明细、检查/序列/影像及识别请求/响应，不只验证Parquet存在。
- 检查隐藏展示字段后必需留存内容仍完整，重复保存不产生重复结果，原始/中间数据仍可查询。
- 检查覆盖声明无需手填，但缺失关系不能静默转普通模式；本条结果状态与任务整体完成情况分别正确显示。
- 检查四组窄/宽布局、折叠摘要、示例标记、真实任务选择、任务结果页与节点预览一致性；模板只读且字段自动绑定，配置页面不产生新的外部模型调用。
- 新发布版本真实Worker执行核心任务；仍明确影像识别为模拟，不把模拟通过当作真实识别效果验收。

### 中文结果的关键验收样例

| 已有事实与逐项结论 | 必须展示 | 不得展示 |
| --- | --- | --- |
| 类别、数量、金额均有效且equal | 本条核验正常，三项一致；双方事实及业务标识 | 因本条正常而声称整个任务所有记录正常 |
| 类别different，数量和金额equal | 明确双方类别及类别差异，数量金额一致 | 固定文案“数量及金额差异” |
| 结算2、识别1、单价10000，类别equal | 数量差-1，金额20000与10000，金额差-10000 | 将识别侧减结算侧改为相反方向，或将金额说成模型识别的金额 |
| 一项或多项尚无有效结论 | 未完成事项及已有原因，保留已知事实 | 把缺失数量填0、把unknown填equal |
| 一项different，另一项unknown | 已确认差异及另一个未完成事项都保留 | 用单一总体状态掩盖已经确认的差异 |
| 尚无实际任务 | 明确标为示例的模板预览 | 真实结果、已落库、核验完成等实际状态 |

以上样例用于验证模板、保存和展示行为，不要求为整张流程新增异常业务分支。

## 设计确认状态

```text
用户已明确：降低配置负担＋中文结果＋必要数据落库＋追溯不可少
├─ Q52 内部管理配置系统化（已同意）
├─ Q53 中文确定性模板及状态（已同意）
├─ Q54 展示/留存分开及结果数据库（已同意）
├─ Q55 四组UI、节点与任务页统一预览（已同意）
└─ Q56 本轮仅预置模板、不开放编辑（已同意）
```

本轮没有待回答的设计问题。索引、事务、外键等常规实现选择按既定业务要求处理，不再转嫁给使用者。代码、数据库和运行画布实施记录见下文。

已确认的架构取舍见[ADR 0005](../../docs/adr/0005-business-result-persistence-and-presentation.md)。

## 证据定位

- src/backend/base/langflow/business/catalog.py:440：Output契约。
- src/backend/base/langflow/business/relational.py:264：选列与系统行标识。
- src/backend/base/langflow/business/datasets.py:77、113、179、210、222：文件与元数据、行追溯。
- src/backend/base/langflow/business/models.py:39—120：版本、任务、输入、数据集、请求、核验统计。
- src/backend/base/langflow/business/coverage.py:10、78、138：声明、任务收尾、逐项核算。
- src/backend/base/langflow/business/runtime.py:373、404、453：来源关联、主结果排序、结果ID保存。
- src/backend/base/langflow/verification/database.py:240：实际Schema映射。
- src/frontend/src/pages/BusinessPage/Tasks.tsx:99、210：默认主结果选择、字段表格。
- 既有结果证据：deploy/business/evidence/compare-configuration-20261015/result-rows.json、image-manifest-rows.json。


## Q52—Q56 实施记录（2026-10-15）

### 已实现

- 核心画布 Results 只保存 `name` 和 `result_template=hip_knee_v1`。发布时由模板生成 44 项必须留存字段与核验覆盖声明；缺失字段或节点绑定时报错。单个 Output 自动作为主结果。
- 删除 Output 顶层无执行作用的 Key fields、Reason fields、Evidence fields；保留覆盖声明中实际使用的原因/证据字段。
- `result_templates/hip_knee_v1.json` 定义业务绑定与留存清单，随发布包保存快照并纳入执行指纹；未修改 11 节点拓扑、比较公式、严格相等口径或模型判定门槛。
- `result_templates.py` 确定性生成中文说明。`results.py` 在任务完成前，将逐条结果及证据在同一事务保存；未到达 Compare 的目标对象也可保存未完成说明，不能默认正常。
- 新增 `verification_scope.business_result`：保存任务/发布版本、输出节点、模板及版本、核验对象和结果数据集/行、状态、完整情况、44 项业务事实、三项检查、当时的中文说明。
- 新增 `verification_scope.business_result_evidence`：保存结果关联的原始数据集/行、识别请求、逐影像检查/序列/申请单与部位判断依据。数据库为平台 PostgreSQL `127.0.0.1:55433/verification`；不写回医院模拟数据源。
- 唯一约束为“任务＋输出节点＋核验对象数据集＋行”。任务行锁与同一事务保证重复保存不重复插入；证据验证/写入失败回滚结果。
- 查询接口：`GET /api/v1/business/tasks/{task_id}/results`、`GET /api/v1/business/tasks/{task_id}/results/{result_id}/evidence`。平台代理使用登录用户归属，监管 API 使用来源隔离；继续通过既有 requests 接口读取原始识别请求/响应。
- Results 配置按“结果模板／结果预览／来源与证据／保存与完整性”组织，支持宽查看。模板只读，无任务时显式标为示例；选择已完成任务读取当时保存的文字。
- 节点预览与任务页共用 `BusinessResultCard`；逐影像证据、留存 JSON 和原始/中间数据表按需展开。查看、翻页、展开证据均不触发流程或模型。
- 新增 37 个前端翻译键，7 个语言文件齐全；中文和英文为本轮完整文案，其余语言使用英文回退文案。

### 运行画布与数据库验收

- 画布：`ce588a72-0614-4d84-badd-0e4355c427e6`，仍为 11 个节点。
- 发布：v10，`165fadce-58d3-4478-955f-2b12b979777e`。核心仅更新 Results 配置；其余活动方案按原已发布图重新验证执行指纹，不采用其未发布草稿。
- 成功验收任务：`7a36ff98-fdc5-4475-ab01-13a5bc59f406`。
- 结算明细 2 条，经检查/序列关联得到 5 条，影像归集后恢复为 2 条耗材对象；髋关节 7 张影像、膝关节 5 张影像。三项比较各 2 条一致，覆盖缺口 0。
- 平台库实际保存 2 条业务结果、38 条证据关联。逐条核对原始来源与识别请求均属于当前任务，识别请求节点为 Observation，原响应存在；重复保存后结果 ID、证据 ID、说明文字和请求数量均不变。
- 此任务使用在线文本模型 2 次，影像识别仍为既有模拟服务。结果说明明确保留模拟标记，不代表真实识别效果已验收。

### 首次验收的模型引用问题

首次任务 `5faee935-476f-43b2-9d8f-f7b0cfc2104c` 中，在线模型将字典原文“右侧股骨前后位(近髋)”引用为“右侧股骨前后位(近骸)”。既有依据检查正确拒绝了该条检查，使髋关节影像为 5 张而非预期 7 张；该任务保留 1 条无法确定记录。结果存储未丢失影像，没有修改规则或门槛来放行错字。保留首次任务与依据记录后，第二次执行通过正常核心样例。这是本次实际观察到的模型输出波动，不能解释为模型永远稳定。

### 验收证据和复验命令

- [核心任务及结果证据](evidence/results-configuration-20261015/acceptance.json)
- [实际数据库审计](evidence/results-configuration-20261015/database-audit.json)
- [已保存中文结果](evidence/results-configuration-20261015/saved-results.json)
- [证据关联](evidence/results-configuration-20261015/saved-result-evidence.json)
- [首次模型引用问题](evidence/results-configuration-20261015/first-run-model-evidence.json)

```bash
# 更新运行画布前：先执行维护入口关闭，确认已接收任务排空。
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/maintenance_local.py close --wait 60
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python -m scripts.business.apply_results_configuration --apply
bash scripts/business/start_local.sh --restart

# 只读复核已完成任务，不再次调用模型。
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python -m scripts.business.verify_compact_core --task 7a36ff98-fdc5-4475-ab01-13a5bc59f406 --evidence-dir deploy/business/evidence/results-configuration-20261015
# 重复保存幂等性检查，不执行流程。
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python -m scripts.business.verify_result_storage
```


### 回归和界面验收

- 相关后端回归：73 项通过；随后补充核对“不完整对象不虚构识别值、重复保存不改写模板版本”，结果持久化专题 10 项再次通过。
- 前端 Business 配置与结果页测试：14 个测试文件、46 项通过。
- 实际 Chromium 验收：1 项整张画布测试通过，覆盖 11 节点既有配置及新增 Results 四组、示例/任务切换、中文窄宽布局、任务页与逐影像证据展开。
- [Results 宽视图](evidence/results-configuration-20261015/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/results-zh-wide.png)
- [Results 窄视图](evidence/results-configuration-20261015/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/results-zh-narrow.png)
- [任务页证据](evidence/results-configuration-20261015/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/saved-result-evidence.png)
- 本轮 Python 改动的 Ruff 检查通过；前端新增组件 Biome 检查通过；新增翻译键在全部 7 个语言文件存在。

- 浏览器验收后再次比对运行画布与发布包，11 节点图完全一致，未残留测试编辑（见 `canvas-audit.json`）。
- 全量 TypeScript 检查定位并修正了两处动态翻译键的类型过宽，以及通用结果名称的错误翻译键；增加新建通用 Output 的命名回归，未变更核心运行口径。

- 全量前端 TypeScript 检查通过（`tsc --noEmit --incremental`）；修复后界面和业务行为保持一致。

- 最终类型检查缓存与全部本轮相关 TSX 文件内容哈希一致，确认检查覆盖最终文件（见 `typecheck.json`）。
- 完整项目已恢复：5 个 HTTP 健康检查均返回 200，6 个后台进程均运行，任务入口 open、待处理任务 0（见 `health.json`）。
