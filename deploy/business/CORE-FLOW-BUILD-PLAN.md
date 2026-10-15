# 正常核心流程：节点搭建与分阶段验收方案

> 2026-10-13 变更：检查与序列改为本地模拟 MySQL 表，结算增加 `SYSTEM_ID`，按申请单和检查标识关联；最新决定与待核对项见[数据库来源变更](./CORE-FLOW-DATABASE-SOURCE-CHANGE.md)。下述三段 API 节点设计需据此修订，不应继续按旧脚本完成画布。

日期：2026-10-12。业务依据：[0929业务图](../../20260921新架构图diagram备份0929.drawio)的“业务流程与节点说明”页，以及本次Q1—Q8和Q4.1/Q4.2的已确认更正。Q8已取代Q6的逐结算窗口规则。

**这是待实施的画布搭建方案，不是整图通过报告。** 数据库样例及独立模拟API已准备；最新Q8已取消日期窗口生成需求。仍需处理数据库时间参数/元数据类型、地址拼接、实际时间比较及必经画布配置，并从空白画布验收。最新实测阻塞及正常路径遗漏见[核心路径复核](./CORE-FLOW-CORE-PATH-REVIEW.md)。完整组件能力清单见[节点审计](./CORE-FLOW-NODE-AUDIT.md)，原字段和接口出处见[数据契约](./CORE-FLOW-DATA-CONTRACT.md)。

## 1. 已确定的业务口径

| 项目 | 本轮约定 |
|---|---|
| 接入 | 结算数据库＋检查/序列/影像API；不建目录数据库 |
| 范围 | 人工髋、膝关节各一组正常样例；从空白业务方案画布搭建 |
| 医院 | 监管传医院名字；结算表按ORGAN_NAME精确匹配；影像请求organ_code取该结算记录的ORGAN_CODE |
| 时间 | UPDATE_TIME为实际结算时间；data[].chk_dt为接口返回的实际检查时间。两类查询共用监管提交的start/end，不再推导前7天窗口；首轮按北京时间、包含两端解释 |
| 影像地址 | 按用户确认的接口契约直接拼接domain＋file_path；账号权限由服务方开通 |
| 名称 | HILIST_NAME包含人工髋关节或人工膝关节；本轮受控名称明确包含这些词，不声称自动覆盖同义词 |
| 类别比较 | 同属髋／膝范围即可，不比较具体型号或名称全文 |
| 数量/费用 | 两侧均按套计；结算金额=CNT×PRIC；观察金额=独立观察数量×同一PRIC；单价元/套 |
| 数据列 | 保留附件50个不同字段；不增加SETL_TIME、源明细金额或单位列；有依据的派生字段在流程中生成 |

首轮每组只有一名虚构患者、一次住院、一条结算明细。因此一个结算明细就是一个核验单元；此简化只覆盖这两组样例。多条明细归并、多个价格、多次手术或重复检查如何计数，留到扩大业务范围时验证。

## 2. 从哪里拖拽

进入[业务方案](http://localhost:3000/business) → 新建方案 → 模板选“空白流程” → 编辑画布。

空白模板自带的`Request`就是`Business Parameters`的实例名称。需要另加时，从左侧Business分类拖`Business Parameters`；调用外部接口则拖`Business Api`。最终发布、启用、提交任务均从绑定的业务方案进入。

本方案使用12种已有组件：Parameters、Database、Validate、Filter、Transform、Api、Union、Aggregate、Join、Imaging、Compare、Output。File、Model、Subflow本轮无需加入。影像地址只需补受限字符串拼接；时间类型/格式对齐属于适配，不增加日期窗口业务规则或专用节点。

下文N01等是搭建清单编号及建议实例名称，不是左侧新的组件类型。保留旧编号便于对照，N07已撤销；实际实例数取决于时间类型对齐和相邻转换能否合并，不以32个节点作为验收目标。不计后续异常输出分支。

## 3. 来源连接和字段依据

| 用途 | 配置 |
|---|---|
| N02数据库 | 连接“模拟结算 PostgreSQL（核心流程）”；schema=`public`；table=`core_flow_settlement_v1` |
| 三段影像API、独立观察模拟 | 连接“模拟影像 API（X-Token）”；base_url=`http://127.0.0.1:8091`；X-Token鉴权，无Bearer前缀 |
| API字段发现 | 使用有出处的文档契约录入所需字段，并显式测试相应接口确认响应；不需要先运行整张workflow |
| 下游字段 | 先接正确输出端口，再从上游推导结构下拉；新输出名只能用于明确的copy、表达式或汇总结果 |

数据库连接ID：`537d8c03-3c9a-4c25-8a8e-d66cfc2b187a`。API连接ID：`bd965b78-e1c6-4553-b884-c78a807b67bc`。

模拟API的三个路径与用户提供的文档一致。8091仅承载本次受控样例；旧8090服务及旧发布版本保留。模型模拟路径`/business/core-flow/imaging`是本项目单独声明的模拟契约，不属于三份Apipost文档。

## 4. 逐节点配置与连接

表中的`.data/.valid/.matched`指来源输出端口；普通节点接Data输入，Join分别接Left data、Right data。Parameters到Database是任务参数依赖，不是结算数据表输入。当前所有组件显示同样输入端口的问题应在实施阶段修正，不能看到端口就任意连接。

### 4.1 任务和结算

| 编号／建议名称 | 拖入组件 | 必需配置 | 来源 |
|---|---|---|---|
| N01 Request | Business Parameters | hospital_name:string、start:string、end:string，均必填；时间约定北京时间YYYY-MM-DD HH:mm:ss；首轮默认值见第8节 | 模板已有 |
| N02 Settlements | Business Database | 上述连接/schema/table；ORGAN_NAME eq参数hospital_name；UPDATE_TIME ge参数start、le参数end；需先修复时间参数类型绑定 | N01.data作为参数依赖，迁移时保留其语义 |
| N03 SettlementChecks | Business Validate | identity.name=`settlement_detail`、namespace=`core-flow-v1`、keys=`ORGAN_CODE,DATA_SOURCE,SETL_FEE_LIST_ID`；必需字段见下文 | N02.data |
| N04 NormalPaid | Business Filter | logic=and；MED_PAY_FLAG eq字符串`1`；LIST_TYPE eq字符串`301`；OP_EM_MARK eq字符串`3`；REFD_SETL_FLAG eq数字`0` | N03.valid |
| N05 TargetNames | Business Filter | logic=or；HILIST_NAME contains `人工髋关节`或`人工膝关节` | N04.matched |
| N06 UnitContext | Business Transform | copy `_business_row_id→unit_row_id`；expression `'套'→unit`；expression `CNT * PRIC→settled_amount`；保留原字段 | N05.matched |
| N07 StudyWindow（撤销） | 不添加节点 | Q8已改为检查API直接引用任务start/end，不再按UPDATE_TIME生成窗口 | N06直接接N08 |

N03当前必需字段：身份三列、PSN_NO、PSN_NAME、CERTNO、OP_EM_MARK、OP_EM_NO、UPDATE_TIME、HILIST_NAME、CNT、PRIC；条件CNT≥0、PRIC≥0。OP_EM_MARK在这里仅检查非空，不要求等于某种就诊类型。医保、耗材、住院、正常收费的业务范围统一由N04筛选；范围外但质量合格的记录进入N04.unmatched，不属于N03.issues。本轮夹具具有这些字段，不据此将生产表所有可空列改为数据库必填。

N02与N08共用N01的start/end；N02筛UPDATE_TIME，N08由模拟接口筛返回检查事实中的chk_dt。本轮采用相同的两个包含边界及北京时间语义。两类记录的时间值不需要相等；不扩大监管提供的范围。通用Parameters目前仅做字符串类型等校验，日期格式和start≤end还需入口检查。

### 4.2 检查查询及部位筛选

| 编号／建议名称 | 拖入组件 | 必需配置 | 来源 |
|---|---|---|---|
| N08 Studies | Business Api | GET `/api/v2/study/list`；请求绑定见下表；响应fields及依据；context_fields见下文 | N06.data |
| N09 StudyChecks | Business Validate，必要时前置Transform对齐时间类型 | required study_primary_id/name/organ_code/op_em_hp_ex_no/chk_dt/ckpt_name；核对姓名、医院、就诊号、就诊类型；模态DR、is_upload=1；实际检查时间在任务范围内；按原图核对本轮住院检查早于结算 | N08.data；原始chk_dt保留，不能用查询边界替换 |
| N10 HipStudies | Business Filter | logic=and；`_context_HILIST_NAME` contains人工髋关节；ckpt_name contains髋关节 | N09.valid |
| N11 KneeStudies | Business Filter | logic=and；`_context_HILIST_NAME` contains人工膝关节；ckpt_name contains膝关节 | N09.valid |
| N12 JointStudies | Business Union | 两个Data输入追加合并；不启用deduplicate，不配置keys | N10.matched和N11.matched |
| N13 StudyContext | Business Transform | copy `_context_unit_row_id→unit_row_id`；保留study_primary_id和后续核对用字段 | N12.data |

N08请求`body`字段在method=GET时作为查询参数发送，配置如下：

| API参数 | 取值 |
|---|---|
| begin_time/end_time | 任务参数start/end；使用请求编辑器的parameter模式，不作为上游字段填写 |
| name/cardno | 上游PSN_NAME/CERTNO |
| organ_code | 上游ORGAN_CODE |
| op_em_hp_ex_mark/op_em_hp_ex_no | 上游OP_EM_MARK/OP_EM_NO；本轮构造住院标记3与同一院内就诊编号 |
| chk_modality | 常量DR，仅为本次模拟模态 |

不发送PSN_CERT_TYPE作为cardtype：未提供RC038码表，不能直接跨码表复制。本轮不需要该可选参数。不发送PSN_NO作为system_patient_id：新模拟接口特意使用不同的影像患者编号，用name/cardno及医院、就诊条件关联。

`context_fields`至少包含`unit_row_id,HILIST_NAME,PSN_NAME,ORGAN_CODE,OP_EM_NO,OP_EM_MARK,UPDATE_TIME`。API会为它们加`_context_`前缀，N09/N10/N11使用该前缀字段。start/end是任务参数，不是数据库列，不应伪造同名来源字段。返回的cardno未在文档中声明，不能凭空配置成响应字段；证件条件的依据来自请求和模拟服务的实际过滤。

N08所需响应字段包括study_primary_id、ris_study_id、name、system_patient_id、organ_code、op_em_hp_ex_mark/no、chk_modality、is_upload、proj_name、ckpt_name、chk_dt。字段类型服从文档：chk_dt是字符串，不应声称它本来就是带时区时间戳。受控模拟返回统一补零格式，可按同格式任务边界检查；与数据库UPDATE_TIME比较前必须明确按Asia/Shanghai解析，不能依赖DuckDB/数据库进程默认时区。这是同一时间事实的格式和类型对齐，不是计算实际检查时间。

### 4.3 序列、影像、清单及回连

| 编号／建议名称 | 拖入组件 | 必需配置 | 来源 |
|---|---|---|---|
| N14 Series | Business Api | GET `/api/v2/dicom/series-instance-uid`；study_primary_id←上游同名字段；context_fields=`unit_row_id,organ_code` | N13.data |
| N15 SeriesChecks | Business Validate | required series_id；organ_code eq right_field `_context_organ_code`；chk_modality eq DR | N14.data |
| N16 SeriesContext | Business Transform | copy `_context_unit_row_id→unit_row_id`；保留series_id | N15.valid |
| N17 Images | Business Api | GET `/api/v2/storage/dicom/sop-instance-uid`；series_id←同名字段；url_type常量`3`；context_fields=`unit_row_id` | N16.data |
| N18 ImageContext | Business Transform | copy `_context_unit_row_id→unit_row_id`；**待补URL构造**：domain＋file_path→file_ref，保留签名查询串 | N17.data |
| N19 ImageChecks | Business Validate | required file_ref、study_instance_uid、series_instance_uid、sop_instance_uid；identity.keys=`unit_row_id,sop_instance_uid`，name=`unit_image`，namespace=`core-flow-images-v1` | N18.data |
| N20 Manifests | Business Aggregate | group_by=`unit_row_id`；collect(file_ref)→image_manifest | N19.valid |
| N21 UnitEvidence | Business Join | keys left.unit_row_id=right.unit_row_id；how=left；cardinality=one_to_one | Left=N06.data；Right=N20.data |
| N22 ObservationInput | Business Transform | 从left_恢复结算字段；right_image_manifest→image_manifest | N21.data |
| N23 EvidenceChecks | Business Validate | required image_manifest；两组清单各包含该组2张模拟影像 | N22.data |

三段API公共配置：`items_path=data`、`method=GET`、`pagination=none`；response_conditions核对code=200及error.error_code=0；`completeness.scope=object`、basis明确写“core-flow-v1受控模拟对每个请求完整返回有限记录”；max_calls可设10覆盖首轮2次请求，触顶必须报告不完整。

本模拟不实现文档中有歧义的分页，传page/page_size会被拒绝，不能把none外推为真实API完整性保证。三个接口响应均按文档留有message/meta及相关标识，不把模型字段混进云影像接口。

必须区分三种标识：

1. `_business_row_id`是当前数据集的内部行号；N06复制成unit_row_id只用于该任务内的透传关联，不作为跨任务业务主键。
2. 每级API的`_request_row_id`只指向直接输入行。影像接口的该字段指向序列行，不能拿它关联最初结算。
3. study_primary_id、series_id是请求下一层的业务API主键；DICOM的study/series/sop_instance_uid是另一些标识，不能互换。

N22恢复至少：unit_row_id、ORGAN_CODE、DATA_SOURCE、SETL_FEE_LIST_ID、PSN_NO、OP_EM_NO、HILIST_NAME、UPDATE_TIME、CNT、PRIC、unit、settled_amount。Join给字段加left_/right_前缀，应从实际输出下拉选取。

影像展开可能产生多行，但结算数量与费用仍保存在N06左支。只对影像清单做Aggregate，再与结算一对一关联，避免因两张影像把1套错误求和成2套。

### 4.4 独立观察和三个比较事项

| 编号／建议名称 | 拖入组件 | 必需配置 | 来源 |
|---|---|---|---|
| N24 Observation | Business Imaging | 上述API连接；path=`/business/core-flow/imaging`；patient_field=PSN_NO、hospital_field=ORGAN_CODE、encounter_field=OP_EM_NO、category_field=HILIST_NAME、unit_field=unit、evidence_field=image_manifest | N23.valid |
| N25 ObservationChecks | Business Validate | recognized_category/recognized_quantity/evidence_ref必需；recognition_confirmed=true；coverage_confirmed=true；recognized_quantity≥0；observed_unit eq right_field unit | N24.data |
| N26 HipCategory | Business Filter | and：HILIST_NAME contains人工髋关节；recognized_category eq人工髋关节 | N25.valid |
| N27 KneeCategory | Business Filter | and：HILIST_NAME contains人工膝关节；recognized_category eq人工膝关节 | N25.valid |
| N28 EqualCategories | Business Union | 追加两路matched；不去重 | N26.matched和N27.matched |
| N29 Amounts | Business Transform | expression `'equal'→category_status`；`recognized_quantity * PRIC→observed_amount` | N28.data |
| N30 CompareQuantityFee | Business Compare | CNT对recognized_quantity；settled_amount对observed_amount；均numeric、严格数值相等（Q50取消容差） | N29.data |
| N31 ResultFields | Business Transform | comparison_0→quantity_status；comparison_1→amount_status；可生成数量/金额差值 | N30.data |
| N32 Results | Business Output | name=核心流程核验结果；primary=true；columns和obligation见下文 | N31.data |

Imaging保留输入字段并附加观察字段，所以不需再做一次结算Join。不配置quantity_field，不把CNT送给模型。新模拟观察服务只按固定患者、就诊与完整影像清单返回预先规定的1套和类别；测试特意给它错误期待类别/数量，观察结果仍不改变。

只有通过髋／膝对应条件的matched行，才写category_status=equal；不能在入口无条件写一致。类别不匹配或缺失的结果以后展开，本轮仍以“2条目标明细对应2条最终结果”防止静默丢行。

N32保留身份三列、HILIST_NAME、UPDATE_TIME、CNT、PRIC、unit、recognized_category/quantity、settled_amount/observed_amount、三个status、evidence_ref、image_manifest、simulated。`obligation.mode=verification`；sources引用N02，identity引用N03；category/quantity/fee三个checks均以N06.data为units，results引用N31.data各自的status字段与evidence_ref。不能用Compare的总体_comparison_status覆盖三个独立事项。

正常样例没有需排除的来源行。若有任一未处理、丢失或无法比较的明细，结果责任不得标为全部交代完成；不能只凭任务completed判通过。

## 5. 已确认缺口与仍需验收的配置

“尚未验收”指：还未从空白Business方案画布完成本轮配置、保存、发布、任务执行及逐项结果核对。它不表示下列每项能力都不存在，也不表示必须修完所有外围表单问题才能进行一次受控运行。数据源/API的39项测试不包含这张新Business画布的完整浏览器操作与执行。

| 缺口 | 实施方向 | 验证 |
|---|---|---|
| 时间适配 | 修复PostgreSQL时间参数被绑定为VARCHAR及带时区元数据丢失；统一实际时间比较的解析语义 | 正确按任务范围读到2条记录，无伪结构变化错误；同一时刻跨时区表示比较一致 |
| 影像地址 | 在受限表达式中支持字符串拼接，例如concat(domain,file_path) | 按已确认契约直接拼接，查询串逐字保留；不扩展URL归一化功能 |
| 端口、条件右值 | 按节点真实能力呈现输入；value/parameter/right_field互斥；数据库条件只允许支持项 | 无效连接及冲突配置在配置/发布时发现 |
| 无效或条件必填项 | 隐藏已禁用Union去重、Imaging.quantity_field及无效Output项；补table/sql、fields/evidence等模式必填 | 用户能从界面完成方案而非手改内部JSON |
| API结构声明（已有能力，待画布配置） | 用新接口响应和文档确认fields/field_evidence；context_fields与请求Body已有字段下拉 | 未运行整图时即可选择真实来源和上游派生字段；过期依据阻止发布 |
| 任务表单 | 保留参数默认值、说明和enum定义；本方案至少正确呈现医院和期间 | 从方案界面提交参数与Parameters声明一致 |

Q8后不再需要日期窗口派生。现有PostgreSQL只读SQL可显式转换任务时间作为高级模式替代，但本轮表模式的源适配问题仍应准确记录，不能把SQL绕行说成表模式已修复。不新增数据库时间列。

旧专用verification流程中的日期偏移不适用于最新Q8；其URL处理也不等于Business Transform已开放字符串拼接。不能以旧流程跑过来替代本轮验收。

## 6. 分阶段实施与验收

| 阶段 | 工作 | 通过标准 |
|---|---|---|
| A 数据源准备 | 原50列建表、2条样例、三段API和独立观察模拟、连接与字段发现 | 数据可实查；两个身份分别贯通检查→序列→2张影像；字段/类型对照文档；观察值独立 |
| B 必经适配与配置整改 | 修复时间参数/元数据、实际时间比较与字符串拼接；修正端口和必经配置问题 | 对应回归测试、发布校验与实际执行语义一致；不要求修完全部外围表单问题 |
| C 空白画布搭建 | 按逐实例清单从Business分类拖拽、配置、连线，跳过已撤销N07 | 保存后无错误，字段下拉正确；不由脚本注入整张业务图替代本项验收 |
| D 发布与执行 | 发布新方案、启用、提交本轮参数 | 新版本实际读取数据库和新API；结算2行、检查2行、序列2行、影像4行、清单2行、观察2行 |
| E 核对与回归 | 检查两个单元的三个事项、来源追溯、持久结果；执行改动相关及Business专项检查 | 2条最终结果、6项equal、数量/金额差值0、没有未交代明细；旧接口与已发布流程不受本次样例准备影响 |

后续异常分支单独扩展；真实DICOM下载/解码、模型准确率、真实供应方分页和生产码表不属于本次模拟通过的结论。

## 7. 本次已准备的数据源证据

- 原字段、表和两条记录：[字段清单](./fixtures/core-flow/settlement-fields.json)、[样例](./fixtures/core-flow/settlement-rows.json)、[数据库验证](./fixtures/core-flow/settlement-seed-report.json)。
- 接口原文依据：[契约摘要](./fixtures/core-flow/imaging-api-contracts.json)。
- 新模拟源码：[core_flow_demo.py](../../src/backend/base/langflow/business/core_flow_demo.py)；专项测试：[test_core_flow_demo.py](../verification/tests/test_core_flow_demo.py)。
- 完整HTTP链路验证记录：[core-api-preparation-report.json](./fixtures/core-flow/core-api-preparation-report.json)。该报告不等于画布运行报告。

## 8. 最终正常结果的独立预期

提交：hospital_name=`核心流程模拟医院`，start=`2025-08-01 00:00:00`，end=`2025-08-31 23:59:59`。本轮按北京时间及包含边界解释；代码适配尚待实施验证。

每次检查API调用使用相同任务范围：2025-08-01 00:00:00至2025-08-31 23:59:59；另带对应患者、医院及就诊条件。实际模拟检查保持2025-08-19 10:00:00，实际结算保持8月20日10:00:00。若监管仅提交8月20日，按Q8应查不到这两条8月19日检查；不能暗中扩大范围或改写chk_dt来使其通过。

| 明细 | 数据库名称 | 观察类别 | 结算/观察数量 | 单价 | 结算/观察金额 | 三项结论 |
|---|---|---|---|---|---|---|
| MOCK-DETAIL-HIP | 人工髋关节（模拟A型号） | 人工髋关节 | 1/1套 | 10000元/套 | 10000/10000元 | 类别、数量、费用均一致 |
| MOCK-DETAIL-KNEE | 人工膝关节（模拟B型号） | 人工膝关节 | 1/1套 | 5000元/套 | 5000/5000元 | 类别、数量、费用均一致 |

这张表是后续验收预期。只有完成阶段C—E并保留相应任务、版本、结果证据后，才能将它标为实际执行结果。

## 9. 面向使用者的问题解释与遗漏检查

### 9.1 最新Q8后的时间适配与地址拼接

- **时间**：已撤销逐结算窗口计算。检查请求直接引用任务参数；实际chk_dt保留接口值。但当前数据库时间参数以VARCHAR绑定会报类型错误，字段元数据还会遗漏时区；与chk_dt比较时也必须明确两侧代表同一时区语义。此类源适配仍需处理。
- **影像地址**：按用户确认的domain＋file_path契约直接拼接。例如https://dicom.invalid与/a.dcm?signature=x%2Fy应得到https://dicom.invalid/a.dcm?signature=x%2Fy。当前表达式的“+”编译为算术，字符串相加失败；concat尚不在白名单。只需补受限字符串拼接，不增加未经要求的地址变换。

begin_time/end_time是由任务参数绑定的API请求参数；unit、settled_amount、file_ref是有明确来源或规则的派生字段。它们不需要预先存在于数据库，也不能被标成数据库原字段。必需的原始来源仍必须存在。

### 9.2 具体表单缺陷

| 问题 | 使用者可能遇到什么 | 本轮处理与影响 |
|---|---|---|
| Database提供不支持的条件 | 在Database中选contains筛HILIST_NAME，发布检查未必拦住，读取时会失败；right_field也未按字段比较执行 | 数据库只提供实际支持的操作，前后端一致校验；当前名称包含筛选放在已有Filter中即可 |
| 条件右值来源不互斥 | 同时填常量和另一个字段，实际优先用字段；也可能残留任务参数覆盖常量。还可能把字段清空成空字符串而非移除属性，导致发布失败 | 增加常量/参数/字段切换及清理；Filter/Validate/Database按实际能力约束 |
| 条件参数自由填写 | 参数名拼错，发布才提示Unknown condition parameter | 改为已声明参数下拉；API Body中的参数下拉已经存在 |
| 端口看起来都能接 | 各节点均显示Data/Left/Right，Data还统一允许多连；实际普通节点、Join和Union的输入规则不同 | 按真实能力展示与限制；Database仍须表达Parameters依赖，不能一概删掉参数入口 |
| Imaging旧项与必填冲突 | quantity_field看起来可填，填写却被拒绝；evidence_field没星号，实际不填不能发布 | 移除期待数量入口，明确证据清单必填；当前正确填写即可运行 |
| Union去重项过时 | 勾deduplicate会阻塞发布，填写keys没有去重效果 | 本轮Union仅追加合并；身份检查在Validate中做 |
| Output旧项不生效 | 填了key_fields/reason_fields/evidence_fields，以为自动建立对应关系或证据，实际上没有该执行效果 | 使用columns决定展示列，obligation说明来源、核验单元和事项结果；整改旧入口 |
| 条件必填/模式引导不足 | copy忘选源字段、cast忘选类型、expression没表达式等，界面没有完整提示；有些错误到发布或运行时出现 | 按操作显示必需项；已有SQL模式隐藏部分无关项，不能说目前完全没有模式切换 |
| 任务提交漏掉枚举与说明 | Parameters限制了允许值，提交界面却仍是自由文本，也缺说明 | 补齐传递和展示；后端枚举校验已有，本轮医院/期间参数可正确手填 |

File的fields条件必填、Model的openai.model条件必填、Subflow版本/输出联动也属全节点审计发现。本轮不使用这些节点，不把它们列为这条正常主链的硬阻塞。

### 9.3 已有能力仍需要正确配置及验收

1. **字段下拉与测试值不同**：下拉来自数据库元数据、API契约/样本或上游结构推导。Transform尚未执行时，下游可以知道输出字段名，却没有该字段的一条实际值。当前预览不会自动运行所有上游；单接口测试可填写请求样例。已知字段名不等于已经取得业务数据。
2. **身份不能混用**：PSN_NO不是天然等于云端system_patient_id；study_primary_id、series_id和各DICOM UID也不能互换。本轮已有明确绑定方案，仍待整图执行核对。
3. **跨层上下文**：API已有context_fields下拉和自动_context_前缀，逐级恢复unit_row_id是具体连线配置；没有证据表明这项能力缺失。最后一层_request_row_id不能直接当原结算行号。
4. **多幅影像不能重复计费**：一条1套结算展开为两张影像，不能因此把CNT求和成2套。先只汇总影像清单，再与保留的结算基准关联。
5. **来源完整性须有依据**：本轮无分页模拟保证每次完整返回有限集合，节点要配置对应completeness；真实供应方分页歧义尚未解决。缺少完整性依据时，平台不能直接把来源当作完整数据。
6. **类别与金额口径**：名称全文不同可以类别一致；同一PRIC下两侧独立数量折算金额，不额外证明原始账单或单价合理性；源字段类型和单位也要按契约保留。
7. **不能只看任务完成**：核对2个单元、每个3个事项，共6个事项结论；不能丢掉一条后只展示另一条的一致结果。还要核对来源、版本、证据及结果持久化。

### 9.4 本轮通过不涵盖的范围

本轮使用固定独立观察夹具，不下载真实DICOM，不验证真实识别准确率。暂不覆盖真实API分页、多明细归并、多价格、多次手术、目录名称同义词，以及缺失、失败、超时等异常分支。首轮通过后再逐项扩展；这些范围不等于全部是当前代码bug。
