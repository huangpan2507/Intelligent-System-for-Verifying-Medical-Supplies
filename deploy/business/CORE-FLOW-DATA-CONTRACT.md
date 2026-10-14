# 正常核心流程：模拟结算表与影像 API 契约

> 2026-10-14 范围变更：用户明确不再要求 OP_EM_MARK=3，已同意将固定业务条件前移 Database、保留 REFD_SETL_FLAG=0，并按查询实际返回范围统计；另说明本场景 HILIST_NAME 是手术名称，CNT/PRIC 记录对应耗材的数量和单价。Q20—Q22 已确认结合手术及耗材信息，采用规则＋大模型辅助，符合依据要求的明确结果自动处理，置信度仅展示；Q23 已指定 SiliconFlow deepseek-ai/DeepSeek-V4-Flash，已实际接入。见[结算范围复核](./SETTLEMENT-SCOPE-REVIEW.md)；新范围已在原画布 v2 实施并完成两条正常样例验收，见[最新实施记录](./CORE-CLASSIFICATION-ACCEPTANCE.md)。下文2026-10-13住院条件为历史记录。

> 2026-10-13 变更：用户已将检查、序列两个来源改为本地模拟 MySQL 表，保留影像列表 API，并要求结算表新增 `SYSTEM_ID`。最新核对记录见[数据库来源变更](./CORE-FLOW-DATABASE-SOURCE-CHANGE.md)。本文下述三段 API 方案及 50 列表描述是变更前的准备记录，不能当作新链路已实施或已验收。

日期：2026-10-12。对应 [节点审计与访谈](./CORE-FLOW-NODE-AUDIT.md)。

用户已确认：髋/膝各一组全一致样例、空白业务画布手工搭建、结算数据库＋影像API混合接入；目录没有对应数据库。用户授权按附件准备一张结算表，并按三份 Apipost 文档准备模拟接口。

当前已完成原始字段建表、连接登记、平台字段读取验证、旧模拟接口差异检查及独立8091模拟API准备。用户随后更正并确认：结算时间使用UPDATE_TIME；按HILIST_NAME名称匹配人工髋/膝关节，不做分类映射；费用按数量×单价比较；模拟统一按套计。撤回新增三个数据库列及编码映射建议。已填入髋/膝两条正常结算样例。最新Q8取代Q6：检查查询也使用监管提交的起止时间，不再计算每条结算前7天的窗口。Q7仍有效，按髋/膝所属范围比较、不核对型号。未创建或发布新的业务画布，也未执行全流程验收。

## 1. 已准备的可用入口

| 资源 | 当前值 | 状态 |
|---|---|---|
| PostgreSQL 地址 | `127.0.0.1:55434` | 复用示例源库，非平台元数据库 |
| 数据库 / Schema / 表 | `business_demo / public / core_flow_settlement_v1` | 已创建，50个不同字段，2条正常结算样例 |
| 数据库连接名称 | 模拟结算 PostgreSQL（核心流程） | 已登记，可在Business Database中选择 |
| 数据库连接ID | `537d8c03-3c9a-4c25-8a8e-d66cfc2b187a` | 平台元数据返回50个匹配的字段 |
| 影像API连接名称 | 模拟影像 API（X-Token） | 已登记；独立于旧Bearer连接 |
| 影像API连接ID | `bd965b78-e1c6-4553-b884-c78a807b67bc` | 地址 `http://127.0.0.1:8091`，`auth_header=X-Token`，空前缀 |

凭据使用本地已有的私有模拟凭据，不复制文档中的示例令牌，不写入本文或契约文件。原 orders/payments、既有API连接、业务画布和发布版本未被覆盖。

建表时的验证记录：[preparation-report.json](./fixtures/core-flow/preparation-report.json)（当时0行）。后续已按用户确认填入2行，见 [settlement-seed-report.json](./fixtures/core-flow/settlement-seed-report.json) 和 [样例记录](./fixtures/core-flow/settlement-rows.json)。建表定义：[settlement.sql](./fixtures/core-flow/settlement.sql)。完整原字段说明及附件指纹：[settlement-fields.json](./fixtures/core-flow/settlement-fields.json)。

用户现在可以先在 Business Database 中选择该连接、`public`、`core_flow_settlement_v1`，查看真实数据库字段。字段发现已验证，2条结算样例也已填入；整图尚未运行。字段下拉本身不依赖表中是否有业务记录。

## 2. 附件结构及建表处理

依据：用户附件 `mock结算信息数据库.docx`；其视图名为 `SETL_INFO`。文件仅包含数据字典，无患者记录、数据库地址或建表语句。

- 附件共54条字段定义、50个不同字段名。
- `SETL_HOS_ID/SETL_MED_ID/MDTRT_SN/MDTRT_ID`各出现两次，两次的类型、长度和必填标记一致；同一物理表各保留一列，并在字段清单保存两个原始行号。
- 附件前段像结算头、后段像明细，但没有给出第二张表名。按用户明确要求的“一张模拟表”，本地采用每行一条明细、附带结算头信息的形式；不据此宣称生产源一定采用相同结构。
- 模拟表的明细身份为 `ORGAN_CODE + DATA_SOURCE + SETL_FEE_LIST_ID`；同一次结算可以有多条明细，因此不把头信息的 SETL_HOS_ID 单独设为此展开表的唯一键。
- 原字段名保留大写；PostgreSQL SQL中引用时需双引号。平台表模式会按真实元数据读取，无需用户手写这些引号。
- 字符串采用TEXT并保留附件最大长度约束；金额/数量采用NUMERIC；“数字10.2”按本地模拟DDL解释为NUMERIC(10,2)，不声称已核实生产库精度。
- UPDATE_TIME 存储类型采用TIMESTAMPTZ，已写入的模拟值显式带时区；用户已明确用它作为本流程的结算时间。这次用户更正取代旧图中不得以UPDATE_TIME作为结算时间的约束，不另建SETL_TIME列。
- 按附件“是否必填”设置非空。说明中的医保结算/退费等条件必填保留为来源规则，样例准备阶段按所选场景核对，不把所有可选字段强制非空。

## 3. 字段用途与本轮模拟约定

| 用途 | 附件字段 | 处理依据 |
|---|---|---|
| 医院统一社会信用代码 | ORGAN_CODE | 可映射到检查查询organ_code；不是12位H码FIX_ORGAN_CODE |
| 姓名 | PSN_NAME | 显式映射为检查查询name |
| 证件号码 | CERTNO | 显式映射为cardno；不是社保卡号 |
| 证件类型 | PSN_CERT_TYPE | 附件引用RC038，未附码表；不能默认与API cardtype相同 |
| 就诊类型 | OP_EM_MARK | 1普通门诊、3住院与API说明可对应；首轮两条样例均为3住院 |
| 就诊编号 | OP_EM_NO | 核对并明确与API op_em_hp_ex_no同一编号；不擅换为MDTRT_SN/MDTRT_ID |
| 患者人员编号 | PSN_NO | 不能仅凭名称认为等于影像系统system_patient_id |
| 是否医保结算 | MED_PAY_FLAG | 附件明确0否、1是；不自动等同某条明细实际基金支付额大于0 |
| 目录类别 | LIST_TYPE | 用户补充码表：101西药中成药、102中药饮片、103自制剂、104民族药、201医疗服务项目、301医用耗材；两条髋膝样例均为字符串`301` |
| 正常收费/退费 | REFD_SETL_FLAG | 附件明确0正常、1退费；本轮正常样例取正常收费 |
| 结算时间 | UPDATE_TIME | 用户已确认，范围查询及后续检查时间窗均以此字段为依据 |
| 项目数量、单价 | CNT、PRIC | Q4.1/Q4.2已确认：数量按套、单价元/套，两侧分别计算数量×单价比较费用 |
| 髋/膝名称范围筛选 | HILIST_NAME | 用户已选择名称模糊/范围匹配，当前不使用编码分类映射或目录API |

### Q4更正：数量、单价、金额和单位的区别

用户截图中的两列符合数量和单价的用途。此前把独立源金额列作为首轮费用比较的必要条件，要求过严；是否需要独立原始金额，取决于要核验什么。

| 概念 | 本例 | 来源或计算方式 |
|---|---|---|
| 项目数量 | 2 | 数据库CNT |
| 项目单价 | 10,000元/套（用户已确认的模拟约定） | 数据库PRIC＋明确的计价口径 |
| 结算侧计算金额 | 20,000元 | CNT×PRIC，是派生金额 |
| 模型观察数量 | 1套 | 独立的模拟观察值，不能由请求中的CNT生成 |
| 观察数量折算金额 | 10,000元 | 观察数量×同一PRIC |
| 费用差额 | −10,000元 | 观察数量折算金额−结算侧计算金额 |

这种比较可以成立，因为两侧数量来自不同依据；两侧都使用同一PRIC并不等于把同一结果与自身比较。它体现数量差对应的费用差，不能额外证明医院原始收费金额正确、单价合理或基金实际支付额正确。只有要独立核对原账单时，才另需来源明细金额，不能把整次结算总额MEDFEE_SUMAMT替代过来。

PRIC说明中的“元”是货币单位，不是CNT采用的套/件/组件。单位可以来自明确、固定的业务约定，不一定要新增数据库列。用户已同意Q4.2：首轮两组构造样例统一按“套”，PRIC按元/套，模型观察数量同样按套；后续不同计量口径再另行处理。截图中的数字10.2是类型精度说明，不表示计量单位。若节点需要输入单位字段，可由Transform按这项已确认规则输出常量字段供下游引用，不冒充数据库原列。

用户已同意Q4.1/Q4.2：不增加原始明细金额列或单位列；数据库维持附件的50个不同字段。结算侧金额和观察侧金额分别派生，不能被标记为原账单核对结论。

### Q5更正：按HILIST_NAME名称范围筛选

用户已选择从数据库HILIST_NAME中匹配人工髋关节、人工膝关节，当前不做分类映射。无需新增目录表、目录API或为这一步增加编码Join。

2026-10-13补充：用户提供LIST_TYPE码表后，先在NormalPaid筛选`MED_PAY_FLAG="1" AND LIST_TYPE="301" AND OP_EM_MARK="3" AND REFD_SETL_FLAG=0`，再由TargetNames匹配HILIST_NAME的髋膝名称范围。LIST_TYPE只确定医用耗材大类，不代替髋膝名称判断；MED_CHRGITM_TYPE是另一字段，不套用本次码表。SettlementChecks只负责初步数据质量，移除其OP_EM_MARK等值条件，保留该字段和非空检查。

现有Business Filter可直接配置如下包含条件；字段从Database上游结构下拉，两个关键词是用户指定的筛选值：

```json
{
  "logic": "or",
  "conditions": [
    {"field": "HILIST_NAME", "op": "contains", "value": "人工髋关节"},
    {"field": "HILIST_NAME", "op": "contains", "value": "人工膝关节"}
  ]
}
```

这里contains是字符串子串包含，不是自动同义词或相似度识别。例如“人工髋关节（某型号）”会命中，“人工全髋关节”不会命中完整子串“人工髋关节”。首轮可用明确包含指定名称的受控样例；更多名称变体以后按实际名称清单补充规则，不能宣称当前两个关键词覆盖所有真实目录名称。

如需要髋/膝分别处理，可以用两个Filter各配置一条包含条件并取matched端口。名称筛选本身不改写原始HILIST_NAME，也不生成编码分类表。后续模型返回的类别仍要按约定的业务范围检查；不能把带型号的项目名称与一个类别名称作全文相等比较，就认为类别一定不同。现有旧模型模拟返回英文类别，适配新样例时须明确其响应词义和比较规则。

## 4. 三份公开API文档的核实结果

本轮已通过文档站公开页面使用的数据接口读取三份原文，不需要登录；没有调用真实医院业务服务。保存的 [结构化契约摘要](./fixtures/core-flow/imaging-api-contracts.json) 包含方法、路径、字段类型、标记及出处，不保存文档示例凭据、患者示例值或签名下载地址。

| 步骤 | 方法与路径 | 必需查询参数 | 列表与衔接 |
|---|---|---|---|
| [检查列表](https://docs.apipost.net/docs/detail/6dfae7d97c79000?locale=zh-cn&target_id=444ee13) | GET `/api/v2/study/list` | 明确的必填项为begin_time/end_time；分页条目有冲突，见下文 | data[].study_primary_id传给下一步 |
| [序列列表](https://docs.apipost.net/docs/detail/6dfae9144079000?target_id=1204a95cb12101&locale=zh-cn) | GET `/api/v2/dicom/series-instance-uid` | study_primary_id | data[].series_id传给下一步 |
| [影像列表](https://docs.apipost.net/docs/detail/6dfaead25070000?target_id=11ffcb2c7120a1&locale=zh-cn) | GET `/api/v2/storage/dicom/sop-instance-uid` | series_id；url_type可选 | data[].domain/file_path及SOP UID组成影像依据 |

三个接口统一用X-token请求头；HTTP头名不区分大小写，连接界面可写X-Token。正常响应为code=200、data数组、error.error_code=0，并包含message及meta.trace。

检查接口的其他查询字段包括name/cardno/organ_code/cardtype/mobile/system_patient_id/chk_modality/op_em_hp_ex_mark/op_em_hp_ex_no/chk_status/is_upload/is_report/is_valid/ris_study_id/sort/order。文档中它们不具有与begin_time/end_time相同的必填标记；接口可选不表示本业务关联时不需要约束患者、医院、就诊和时间。

### 响应结构

- 检查记录：检查主键、医院、患者内部编号、姓名、性别、年龄、就诊类型与编号、检查模态、状态、是否上传、项目名、检查方法、部位、检查时间、医生、报告信息等。业务主链直接需要study_primary_id、organ_code、op_em_hp_ex_no、chk_modality、proj_name、ckpt_name、chk_dt及相应身份依据。
- 序列记录：series_id、organ_code、pacs_study_id、pacs_series_id、series_number、chk_modality。
- 影像记录：image_instance_number、file_path、file_size、domain、study_instance_uid、series_instance_uid、sop_instance_uid、file_suffix。

检查的report_list是嵌套数组，thumb_images仅有null示例；不能据此推断任意非空结构。首轮不依赖这两个字段作专业判断，原始响应仍按平台约定留存。

`study_primary_id`不等于`pacs_study_id`或`study_instance_uid`；`series_id`不等于`pacs_series_id`或`series_instance_uid`。下游请求必须用正确字段，同时用context_fields保留上游业务关联。

用户已确认本接口的影像地址为 `domain + file_path` 直接拼接，保留file_path中的查询参数；服务方开通账号权限后可访问。首轮只实现此已确认契约，不额外引入绝对路径识别或其他URL组合规则。首轮模拟不能使用文档中的真实示例下载地址，也不以构造模拟引用代替真实影像下载验证。

`data[].chk_dt` 是接口返回的实际检查时间，例如 `2023-06-12 17:44:37`，应原样保留。请求的 `begin_time/end_time` 是在调用接口之前提供的查询条件，并非计算出来的检查事实。最新Q8已确认：结算查询与检查查询共用监管提交的开始、结束时间，取代此前逐结算前7天至当天的规则；医院名字用于结算表ORGAN_NAME精确筛选，返回记录中的ORGAN_CODE再绑定检查请求organ_code。两类记录各自使用自己的实际时间字段筛选，不要求结算时间等于检查时间。

本轮模拟时间文本为北京时间 `YYYY-MM-DD HH:mm:ss`，查询两端包含边界；首轮任务范围改为 `2025-08-01 00:00:00` 至 `2025-08-31 23:59:59`，覆盖现有8月19日检查和8月20日结算，不修改夹具中的真实记录时间。PostgreSQL带时区列的参数绑定及元数据保真问题见[核心路径复核](./CORE-FLOW-CORE-PATH-REVIEW.md)，尚未修复。真实服务文档未充分说明时区和边界，不能以模拟约定冒称生产服务保证。

### 文档本身的歧义

检查分页有两组page/page_size：一组page描述为调用方计算 `(page-1)*page_size`，另一组描述为数字页码，必填标记也不同；四条都是未勾选条目。因此本轮不能把真实分页协议说成已经确定。

三份正常响应没有total/has_more/next_cursor/complete标志。受控模拟可约定有限数据完整返回，并在节点completeness中明确其依据来自模拟实现；不能把这个保证冒充真实服务已经提供的承诺。本轮独立模拟采用无分页的完整有限记录集合，传page/page_size会明确拒绝，不猜测真实服务的分页规则。

序列参数study_primary_id的说明误写“患者名字”，影像series_id说明写“检查id”；这类复制残留记录为文档冲突，按字段名与三级接口关系设计绑定，不照错误说明改成姓名。

## 5. 旧模拟API的差异及新模拟服务

本机8090已有三条同路径接口。本轮真实HTTP调用旧膝关节夹具得到：检查1条、序列1条、影像2条，均HTTP200、code=200、error.error_code=0。

但它们尚不完整符合用户本次指定契约：

| 检查项 | 本轮实测 |
|---|---|
| 按文档提供时间与name/cardno查询 | 返回422；旧模拟额外强制要求system_patient_id、organ_code、chk_modality、op_em_hp_ex_mark、op_em_hp_ex_no |
| 检查响应字段 | 缺name/organ_name/sex/age/chk_status/chk_methodname/chk_doc_name/is_report/report_list/thumb_images |
| 序列记录 | 六个声明字段齐全 |
| 影像记录 | 缺file_size/file_suffix |
| 公共响应包装 | 三者均缺message/meta |
| 与新结算字段兼容 | 旧夹具机构值为synthetic-hospital，不满足附件18位机构码要求；旧身份不能直接伪装成新表样例 |

证据：[existing-demo-contract-audit.json](./fixtures/core-flow/existing-demo-contract-audit.json)。这里只验证了旧模拟服务可调用及其差异，未生成新的全流程任务。

为避免改变旧专用核验发布包的源码指纹，新模拟服务独立运行于8091，三段路径与文档相同；8090保持原状。此前新建但尚未被方案/发布引用的X-Token连接已指向8091，连接ID不变。没有改动旧Bearer连接、旧画布、旧发布版本。

新模拟实现补齐了上述文档响应字段，支持begin_time/end_time及本轮使用的name/cardno、organ_code、system_patient_id、chk_modality、op_em_hp_ex_mark/no过滤。检查姓名与证件对应表来自本轮合成身份，影像患者编号特意不同于结算PSN_NO。其余文档可选查询功能（例如分页、排序、其他状态过滤）未实现，传入会返回422；不冒充完整生产接口。

每组返回1个检查、1个序列、2张影像。所有结果标记simulated。file_path包含相对路径与模拟签名查询串，domain为dicom.invalid；没有实际DICOM文件。url_type接受文档列出的值，本模拟统一返回同一组无真实下载内容的引用，不验证不同网络下载方式。

独立观察模拟为POST `/business/core-flow/imaging`，同样使用X-Token。请求患者、医院、就诊与完整影像清单匹配后，按固定观察夹具返回人工髋/膝关节、1套及证据引用。缺失部分清单不会确认覆盖；观察值不从期待类别、CNT或请求单位复制。该路径是项目自己的模拟协议，并非Apipost提供的第四个接口。

源码：[core_flow_demo.py](../../src/backend/base/langflow/business/core_flow_demo.py)。测试及本地HTTP/运行前字段预览证据：[core-api-preparation-report.json](./fixtures/core-flow/core-api-preparation-report.json)。专项接口、契约及旧流程回归共39项通过；本轮未因此执行整张Business画布。

平台预览已实际返回检查22个、序列6个、影像8个字段。检查中的report_list是嵌套数组，thumb_images在样例中全为空，平台仍将二者标为类型待确认；核心流程不使用这两个字段，只绑定契约明确的必要标量字段。没有把不确定的字段自动当作可执行文本字段。

## 6. 本轮执行边界与下一步

- 已做：原50列表及2条样例、两个独立连接、真实数据库字段读取、三份文档解析、8091三段API和独立观察模拟、接口与旧流程回归、平台显式API字段预览、设计文档。
- 已确认更正：UPDATE_TIME作为结算时间；HILIST_NAME作为名称范围筛选来源，当前不采用分类映射。
- 已确认Q4.1/Q4.2：以数量×单价进行费用比较，首轮统一按套计；无需新增数据库列。
- 已确认Q8取代Q6：检查查询与结算查询共用监管提交的起止时间，模拟按Asia/Shanghai解释；不再推导前7天窗口。Q7仍有效：类别按髋/膝所属范围判断，具体型号不在首轮比较范围。
- 业务口径已收敛；下一步按[最终搭建方案](./CORE-FLOW-BUILD-PLAN.md)补齐必要节点能力，再进行画布验收。
- 后续实施：数据库时间绑定/时区元数据、请求时间格式适配、受限字符串拼接，以及必经表单与发布校验整改；从空白业务画布逐项搭建、发布、提交，核对2条结果和6项一致结论。Q8后不再新增日期窗口功能。

原字段表和模拟API是用户明确授权的独立准备工作，已经执行。数据源验证通过与整图验收通过分开记录；这次正常模拟结论不外推为生产码表、真实分页或模型效果已通过。

## 7. 附件50个不同字段与本地类型

下表“必填”按附件列原文；“否”仍可能在描述中有医保结算等条件必填要求，详见字段JSON。

| 原字段名 | 含义 | 本地类型 / 字符长度上限 | 必填 | 附件表格行 |
|---|---|---|---|---|
| `ORGAN_CODE` | 采集医疗机构代码 | TEXT，最大18字符 | 是 | 3 |
| `ORGAN_NAME` | 采集医疗机构名称 | TEXT，最大80字符 | 是 | 4 |
| `ORGAN_ADMDVS` | 医疗机构医保区划 | TEXT，最大6字符 | 是 | 5 |
| `ORGAN_LV` | 医疗机构等级 | TEXT，最大6字符 | 是 | 6 |
| `FIX_ORGAN_CODE` | 定点医药机构编号 | TEXT，最大12字符 | 是 | 7 |
| `FIX_ORGAN_NAME` | 定点医药机构名称 | TEXT，最大80字符 | 是 | 8 |
| `DATA_SOURCE` | 信息系统院内唯一ID | TEXT，最大16字符 | 是 | 9 |
| `SETL_HOS_ID` | 院内结算id | TEXT，最大80字符 | 是 | 10,36 |
| `INIT_SETL_HOS_ID` | 原院内结算id | TEXT，最大80字符 | 否 | 11 |
| `SETL_MED_ID` | 医保结算id | TEXT，最大80字符 | 否 | 12,37 |
| `INIT_SETL_MED_ID` | 原医保结算id | TEXT，最大80字符 | 否 | 13 |
| `MDTRT_SN` | 就医流水号 | TEXT，最大100字符 | 是 | 14,38 |
| `MDTRT_ID` | 就诊id | TEXT，最大30字符 | 否 | 15,39 |
| `MED_PAY_FLAG` | 医保结算标识 | TEXT，最大2字符 | 是 | 16 |
| `PSN_NO` | 患者人员编号 | TEXT，最大64字符 | 否 | 17 |
| `PSN_NAME` | 患者姓名 | TEXT，最大40字符 | 是 | 18 |
| `PSN_CERT_TYPE` | 患者证件类型 | TEXT，最大2字符 | 是 | 19 |
| `CERTNO` | 患者证件号码 | TEXT，最大24字符 | 是 | 20 |
| `SOC_SEC_CARD_NO` | 社会保障卡卡号 | TEXT，最大36字符 | 否 | 21 |
| `GEND` | 性别代码 | TEXT，最大1字符 | 是 | 22 |
| `OP_EM_MARK` | 门诊/急诊/住院/体检标识 | TEXT，最大12字符 | 是 | 23 |
| `OP_EM_NO` | 门诊/急诊/住院/体检编号 | TEXT，最大36字符 | 是 | 24 |
| `RCD_DT` | 收费/退费日期时间 | TEXT，最大15字符 | 是 | 25 |
| `REFD_SETL_FLAG` | 退费结算标志 | NUMERIC(1,0) | 是 | 26 |
| `MED_TYPE` | 医疗类别 | TEXT，最大12字符 | 否 | 27 |
| `MEDFEE_SUMAMT` | 医疗费总额 | NUMERIC(16,2) | 是 | 28 |
| `FUND_PAY_SUMAMT` | 基金支付总额 | NUMERIC(16,2) | 否 | 29 |
| `PSN_PART_AMT` | 个人负担总金额 | NUMERIC(16,2) | 否 | 30 |
| `ACCT_PAY` | 个人账户支出 | NUMERIC(16,2) | 否 | 31 |
| `PSN_CASH_PAY` | 个人现金支出 | NUMERIC(16,2) | 否 | 32 |
| `HOSP_PART_AMT` | 医院负担金额 | NUMERIC(16,2) | 否 | 33 |
| `UPDATE_TIME` | 最终结算时间 | TIMESTAMPTZ | 是 | 34 |
| `SETL_FEE_LIST_ID` | 结算明细id | TEXT，最大80字符 | 是 | 35 |
| `RPT_NO` | 申请单编号 | TEXT，最大512字符 | 否 | 40 |
| `FEEDETL_SN` | 费用明细流水号 | TEXT，最大36字符 | 是 | 41 |
| `INIT_FEEDETL_SN` | 原费用明细流水号 | TEXT，最大80字符 | 否 | 42 |
| `HOS_PROJ_NO` | 院内项目编码 | TEXT，最大200字符 | 是 | 43 |
| `HOS_PROJ_NAME` | 院内项目名称 | TEXT，最大1000字符 | 是 | 44 |
| `HILIST_CODE` | 医保目录编码 | TEXT，最大36字符 | 否 | 45 |
| `HILIST_NAME` | 医保目录名称 | TEXT，最大36字符 | 否 | 46 |
| `LIST_TYPE` | 目录类别 | TEXT，最大36字符 | 否 | 47 |
| `MED_LIST_CODG` | 医疗目录编码 | TEXT，最大36字符 | 否 | 48 |
| `MEDINS_LIST_CODG` | 医药机构目录编码 | TEXT，最大36字符 | 是 | 49 |
| `MEDINS_LIST_NAME` | 医药机构目录名称 | TEXT，最大36字符 | 是 | 50 |
| `MED_CHRGITM_TYPE` | 医疗收费项目类别 | TEXT，最大36字符 | 否 | 51 |
| `PRODNAME` | 商品名 | TEXT，最大36字符 | 否 | 52 |
| `SPEC` | 规格 | TEXT，最大36字符 | 否 | 53 |
| `DOSFORM_NAME` | 剂型名称 | TEXT，最大36字符 | 否 | 54 |
| `CNT` | 项目数量 | NUMERIC(10,2) | 是 | 55 |
| `PRIC` | 项目单价（元） | NUMERIC(10,2) | 是 | 56 |

## 8. 已写入的两条正常结算样例

| 明细 | HILIST_NAME | CNT（套） | PRIC（元/套） | CNT×PRIC（元） | UPDATE_TIME（北京时间） |
|---|---|---|---|---|---|
| MOCK-DETAIL-HIP | 人工髋关节（模拟A型号） | 1 | 10000.00 | 10000.00 | 2025-08-20 10:00:00 |
| MOCK-DETAIL-KNEE | 人工膝关节（模拟B型号） | 1 | 5000.00 | 5000.00 | 2025-08-20 10:00:00 |

已在真实PostgreSQL读取验证：两行均被HILIST_NAME的目标名称条件命中，计算金额分别为10000和5000。每个样例是一名虚构患者的一次虚构住院及一条结算明细；机构、证件、目录等标识均是模拟值。没有把未提供的正式码表内容伪装成已验证的真实编码。检查查询窗口按已确认规则为2025-08-13 00:00:00至2025-08-20 23:59:59（北京时间）。

PostgreSQL可能以UTC返回UPDATE_TIME，报告中的2025-08-20 02:00:00+00:00与北京时间10:00是同一时刻；时间窗口须先按Asia/Shanghai取得结算日期。费用单位约定留在流程配置中，未增加数据库列。
