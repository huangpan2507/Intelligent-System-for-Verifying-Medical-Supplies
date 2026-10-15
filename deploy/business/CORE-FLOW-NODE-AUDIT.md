# Business 节点与正常核心流程审计

日期：2026-10-12。

状态：Q1—Q5及Q4.1/Q4.2已明确：数据库＋API、空白画布搭建、正常髋/膝样例、UPDATE_TIME结算时间、HILIST_NAME名称筛选、数量×单价费用比较、统一按套计；不增加此前提议的三个数据库列，不建立分类映射。Q6检查时间窗、Q7类别比较口径均已确认。已建立50个原字段的模拟表、填入两条正常样例并登记两个连接，并验证数据库字段发现；新增8091独立模拟API及运行前字段预览，39项相关测试通过。未修改业务画布或发布版本，未提交新的核验任务。候选搭建方案尚未完成实现与验收。

## 1. 审计范围与结论

本轮以 [20260921新架构图diagram备份0929.drawio](../../20260921新架构图diagram备份0929.drawio) 的“业务流程与节点说明”页为依据，页面 ID 为 `implementation`，从文件第 160 行开始。不是另一份旧 drawio，也不以旧专用 verification 流程的能力代替当前 Business 流程。

用户已确定：重新梳理所有节点与配置，先验证模拟场景的正常核心流程，再展开异常分支。此前 [字段绑定 Q1—Q6](./FIELD-BINDING-DESIGN.md) 和 [通用平台 D01—D07](./REFACTORING-PLAN.md) 继续有效，不重复征询。

当前用户决定优先于图中旧约定：结算时间使用UPDATE_TIME；本轮使用HILIST_NAME名称范围筛选，不要求目录编码映射；费用比较按两侧数量乘同一PRIC计算，不另加原始账单金额核对目标。原始drawio保留，本文记录本次更正。

当前结论：

1. 左侧真实存在 **15 种 Business 组件**。`Request` 是 `Business Parameters` 的实例名称，不是漏注册的组件。
2. 通用读取、关联、汇总、比较和结果持久化能力已有基础；现有耗材模板有 53 个实例，不能把它当作正常核心流程的最小搭建清单。
3. 指定业务图要求的检查时间窗、患者查询映射、检查部位初筛、完整影像清单及部分费用规则，没有被现有模板完整表达。
4. 若干配置项与实际执行能力不一致，包括数据库条件、无效输入端口、已禁用的去重和识别期待数量配置。
5. 旧版本有一条膝关节记录走完整条比较链的证据；没有“最新版本＋纯正常样例＋用户从空白画布搭建”全通过的证据。不能据此宣布本轮目标已经实现。

## 2. Request 在哪里，实际如何添加节点

三个概念必须区分：

| 名称 | 实际含义 | 用户操作 |
|---|---|---|
| `Business Parameters` | 左侧可拖拽的组件类型；内部类型 `parameters` | 声明任务输入参数的名称、类型、必填、默认值和允许值 |
| `Request` | 模板给这个参数节点起的实例名称 | 可以沿用，也可以改为“任务入参”；改显示名称不会增加能力 |
| 外部任务请求 | 调用方提交一次业务任务，由公共任务 API 受理 | 提交方案代码与参数；不是在画布拖入一个 HTTP 监听器 |

当前可用的搭建入口：

1. 打开 [业务方案](http://localhost:3000/business)。
2. 新建方案，填写名称、稳定编码、允许的调用来源，模板选择 **“空白流程”**。
3. 点击该方案的“编辑画布”。空白模板实际上自带一个 `Request`，其类型就是 `Business Parameters`。
4. 若参数节点已存在，直接配置它；若需要添加，从左侧 **Business → Business Parameters** 拖入。其他节点也按本文中的真实组件名称查找。
5. 选中对应节点，在右侧业务配置面板配置，连接所需端口，等待画布保存。
6. 返回绑定的业务方案，检查并发布已保存画布、启用版本、填写任务参数并提交。

不要把独立的“New Flow”与业务方案绑定画布混为一谈：当前新建业务方案接口会创建自己的 `flow_id`，没有直接选择既有独立画布的入口。

也不能用其他分类的普通 `API Request` 组件直接替代 `Business Api`：当前业务发布只接受已注册的 Business 能力及对应组件代码。**读取外部接口应拖 `Business Api`；声明外部任务参数应拖 `Business Parameters`。**

普通画布节点的运行按钮并不是这套持久业务任务的验收入口。Business 组件需要已发布业务方案和任务运行上下文。

代码依据：`templates.py:174,545`、`components.py:18,31,129`、`api/v1/business.py:56`、`Schemes.tsx:74`。本轮在线 `/api/v1/all` 确认 15 种组件，`/api/v1/business/templates` 确认 compare、consumables、empty 三个模板。

## 3. 全部 15 种节点的配置清单

“必须”包含业务、发布和运行条件，不能只看当前表单的星号。“本轮可省”表示该场景无需使用，不表示可以删除平台能力。

| 左侧组件 | 必须／条件必须的配置 | 可选、模式相关或本轮可省 | 核查结果 |
|---|---|---|---|
| **Business Parameters** | 使用参数时，`parameters[]` 每项 `name/type`；按业务明确 `required` | `default/enum/description`；`dataset_fields` 用于接收子流程输入数据，普通任务入口不需要 | 任务表单没有完整呈现 enum，见 F05 |
| **Business Database** | `connection`；`table` 或 `sql`；SQL 模式要预览确认 `fields/field_evidence`，占位符对应 `parameters[]` | 表模式 `schema/conditions`；真实表列自动发现。SQL 模式不使用表模式条件 | 数据库条件支持范围与表单不一致，见 F01；不能手填 fields 捏造表列 |
| **Business Api** | `connection/path/fields` 与有效 `field_evidence`；必要请求参数放 `body`；非根数组设置 `items_path`；完整核验需要 `completeness.basis/scope` | `method` 默认 GET；`pagination` 默认 none。分页时配置 `cursor_path/cursor_parameter/page_parameter` 等；`max_calls/max_pages`；`context_fields`；`response_conditions`；完整性标志 `complete_path` | 分页必须服从接口契约，不能随意切换；携带上游字段与响应字段是两类配置 |
| **Business File** | `file_id/format`；发布实际要求非空 `fields`，正常上传会生成 | CSV／JSON／Parquet；`encoding`。已有 API／DB 来源时，本轮无需此节点 | fields 的实际必需性未完整体现为表单必填 |
| **Business Transform** | 每条转换 `output/operation`；copy/cast/map 要 `field`；cast 要 `type`；map 要 `mapping`；expression 要 `expression` | `select` 空表示保留原字段；数值精度 `precision/scale`；无转换需求可省实例 | 条件必填不清晰；没有专门的日期窗口配置，不能直接承诺已支持图中的时间推导 |
| **Business Validate** | 按职责配置 `required/unique/conditions`；业务身份去重需要 `identity.name/namespace/keys` | 普通结构检查可以不声明业务身份；无规则只是空校验 | 正常链仍需身份、关键字段和比较前提校验；本轮只让构造数据走 valid 端口 |
| **Business Filter** | `conditions[]` 的 `field/op`；普通比较的右值来自常量 `value`、任务 `parameter` 或 `right_field` | `logic` 默认 and，可选 or；is_null/not_null 不需要右值 | 空条件全放行；当前能同时填多个右值来源，存在歧义，见 F06 |
| **Business Join** | 左右两份数据；非空 `keys[]`，每项 `left/right` | `how` 默认 full；`cardinality` 默认 one_to_one；本业务应明确实际关联方式和基数 | 目录多对一、检查一对多等不能盲用默认；输出前缀字段应从下拉选择 |
| **Business Aggregate** | 非空 `metrics[]`，每项 `operation/output`；除 count(*) 等情况外明确 `field` | `group_by` 空表示整体汇总；sum/count/min/max/avg/collect | 分组口径属于业务配置；分页不是分组；成员关系必须保留 |
| **Business Compare** | 非空 `comparisons[]`，每项 `left/right` 来自当前同一输入表 | `mode` exact／numeric／case_insensitive；numeric 按数值相等比较，不支持容差（Q50）；`null_equal` 默认 false | 两份数据先 Join；类别、数量、费用分别配置比较事项 |
| **Business Model** | `connection/input_fields/fields`；openai 模式还实际需要 `model` | `mode`、`path`、`prompt/max_calls`；structured 模式请求协议为 record/prompt/output_fields | 本图的规则部位初筛不用通用大模型；专业识别优先核对 Imaging 适配；openai 的条件必填不完整 |
| **Business Union** | 一份或多份 Data 输入 | 当前作用是追加合并 | `deduplicate=true` 已禁止；`keys` 不参与执行，不应作为有效去重配置展示 |
| **Business Output** | `name`；流程至少一个 Output。核验场景须在主 Output 声明 `obligation` 的来源、身份、事项和结果引用 | `columns` 空表示全部；`primary` 至多一个；普通数据处理可使用 ordinary | `key_fields/reason_fields/evidence_fields` 当前不参与结果计算；真正的结果责任在 obligation，见 F03 |
| **Business Subflow** | `release_id/output_node`；子版本需要输入数据时，接入满足 `dataset_fields` 契约的数据集 | `parameters` 映射；本轮可以先展开节点，不必封装子流程 | 运行能力已有；已发布版本与输出节点缺少联动选择入口 |
| **Business Imaging** | `connection/path/patient_field/category_field/unit_field/hospital_field`；编译还必须有 `evidence_field` | `encounter_field/max_calls` | `quantity_field` 已禁止，不能把待核验数量传给模型；evidence_field 未正确标必填。输出结构目前固定，完整专业清单需要核对适配 |

共同字段声明支持 `name/type/nullable/required/precision/scale/timezone/unit`。是否允许省略与值是否允许 null 分开表达。来源字段名必须有依据；映射、表达式和汇总可以声明新的输出名，但不能据此凭空增加来源字段。

### 配置位置与字段来源

| 配什么 | 放在哪里 | 字段从哪里来 |
|---|---|---|
| 数据库/API/模型地址与凭据 | 连接管理 | 节点选择登记的连接，不重复填密码 |
| 医院、结算开始/结束等任务入参定义 | Parameters | 参数定义；单次值在提交任务时填写 |
| 数据库表列 | Database 表模式 | 真实数据库元数据，不要求先运行整图 |
| SQL 输出列 | Database SQL 模式 | 显式 SQL 预览并确认类型 |
| API 响应字段 | Api 的接口契约／显式测试入口 | 服务方结构、带出处的文档录入，或实际响应样本 |
| 请求参数值 | Api 请求配置 | 常量、任务参数、上游字段；对象/数组可组合 |
| 下游校验、关联、汇总、比较字段 | 对应节点 | 实际连线所接输出端口的推导结构 |
| 最终结果交代责任 | 主 Output | 引用来源、身份定义、核验单元和各事项结果 |
| 方案选择和调用授权 | 业务方案／任务受理 | 选择方案及已启用版本，不在每个节点重复配置 |

## 4. 以指定业务图为入口的候选搭建顺序

以下是**职责映射与待补齐内容**，不是可以无条件照抄并立即运行的配置配方。数据库/API接入、金额、单位、时间和类别口径已确认；最新Q8取代Q6，检查查询与结算查询共用监管起止时间。必经缺口见[核心路径复核](./CORE-FLOW-CORE-PATH-REVIEW.md)，再按清单验证每个实例、字段和连线。

```text
Parameters：任务入参
  → Database：按医院与UPDATE_TIME读取结算范围
  → Validate：明细身份及基础字段
  → Filter：医保结算、正常收费
  → Filter：HILIST_NAME包含人工髋／膝关节（按需分别处理）
  → Transform / Validate：单位约定为套、结算侧金额=CNT×PRIC
  → 建立核验单元及结算基准（多明细归并时再配置Aggregate）
       ├────────────── 保留类别／数量／单价／金额基准 ─────────────┐
       → 绑定检查查询条件：任务起止时间、患者、医院与就诊        │
       → Api：检查列表                                         │
       → Validate / Filter：身份、时序、模态、部位规则〔待补齐〕│
       → Api：序列列表                                         │
       → Api：影像地址列表                                     │
       → Validate：影像身份与必需信息                           │
       → Aggregate：证据清单                                   │
       → Join：证据与核验单元                                  │
       → Imaging：取得独立模拟观察值                            │
       → Validate / Filter：各事项比较前提                      │
       → Join／保留字段：对齐结算基准 ←─────────────────────────┘
       ├→ 类别范围检查（同属髋／膝） → Output：类别结果
       ├→ Compare：数量 → Output：数量结果
       └→ Transform：有依据的折算金额 → Compare：费用 → Output：费用结果
```

此图按职责表示依赖，具体是否需要额外 Join 取决于前序节点保留的字段。一个图中业务框可以对应多个实例。不能为了凑成“每个业务框一个节点”发明不存在的组件，也不能假设 Aggregate 会保留所有未分组、未聚合字段。

| 原图步骤 | 对应组件 | 必须保留的配置与数据 | 现状 |
|---|---|---|---|
| 00 受理/上下文 | 任务 API＋Parameters | 医院、医保结算期间、方案选择；任务与发布版本由受理层固定 | 已有基础；不需要新增 Request 组件 |
| 01 结算读取 | Database | 医院＋UPDATE_TIME范围、明细身份、患者、就诊、CNT、PRIC、HILIST_NAME | 新表和两条正常结算样例已准备；画布待搭建 |
| 02 筛选与归类 | Validate、Filter，按需Transform | MED_PAY_FLAG、REFD_SETL_FLAG、HILIST_NAME名称条件、数量、单价、固定套计口径 | 用户选择名称范围筛选，无需目录API或分类编码Join |
| 03 关联检查 | Api，直接引用任务起止参数 | `name/cardno/organ_code/chk_modality`、就诊信息、`begin_time/end_time`；cardtype无可靠映射则不传 | Q8取消逐结算窗口；新模拟支持姓名/证件＋医院/就诊关联；画布绑定待搭建 |
| 04 部位初筛 | Validate／Filter，必要时显式映射 | `chk_dt/proj_name/ckpt_name` 与目标关节规则；保留检查主键 | 当前仅检查模拟 `scope_confirmed`，缺少显式部位规则 |
| 05 序列与影像 | Api×2、Validate、Aggregate | 检查→序列→影像UID与地址；去重范围；业务单元、任务与证据关联 | 三段读取有模拟实现；现清单仅 collect file_ref，未完整表达图中对外清单 |
| 06 小模型 | Imaging，按响应增加 Validate | 证据、患者/就诊/医院/类别/计数单位、请求号；返回观察值与依据、处理清单及版本 | 当前固定合成JSON响应，模拟值独立于期待数量；完整专业协议仍有差距 |
| 07 分项比较 | 类别范围检查、Compare、Transform，必要时Join | 数量均按套；结算金额=CNT×PRIC，观察金额=独立观察数量×同一PRIC；类别按髋/膝所属范围判断 | 旧模板不是新字段配置；此次不增加原账单金额核对目标 |
| 08 保存汇总 | Output＋公共结果服务 | 明细去向、单元结论、证据、事项、版本与持久结果 | 已有主结果责任与多个输出表；需本轮新验收 |

**本轮不必为“覆盖所有节点”加入 File、Model、Subflow。** 最终展开方案使用Union追加合并髋/膝正常分支，不启用去重。Database已确定用于结算；通用Model不等于专业Imaging。平台能力清单与本业务必要实例清单是两个层次。

### 三段影像接口的目标契约

图第 174、180 行的目标约定为：

1. `GET /api/v2/study/list`：按患者、医院、就诊、模态和时间窗查检查，获得 `study_primary_id`。
2. `GET /api/v2/dicom/series-instance-uid`：参数 `study_primary_id`，获得 `series_id`。
3. `GET /api/v2/storage/dicom/sop-instance-uid`：参数 `series_id`，可选 `url_type`，获得 `domain/file_path/影像UID`。

原图写作`SETL_TIME＋窗口配置`；先前Q6采用UPDATE_TIME前7天窗口，但最新Q8已明确取代：begin_time/end_time直接引用监管任务起止时间，不再逐结算推导。UPDATE_TIME仍是用户确认的结算时间；chk_dt仍是检查返回事实，两者都不被查询边界替换。`cardtype=01`只能在证件类型确认为身份证时配置；op_em_hp_ex_no要有对应的院内编号依据；RPT_NO不作为该请求参数。

旧模板使用 `/business/studies`、`/business/series`、`/business/images`。本轮新增8091服务使用上表三个文档路径，连接和验证结果见数据契约。旧 [影像契约说明](../verification/imaging-api-contract.md) 描述过专用 verification 实现；其中的自动时间窗不能算作当前 Business 已经实现。模拟服务可以验证上述契约，但其结构依据须明确标为构造契约，不能冒称真实供应方已联通。

影像下载、解码和专业识别属于模型服务，不是 Business Api 的职责。本轮模拟验证编排与数据传递；仍需保留模型模拟标记。

## 5. 已发现的配置缺陷与缺口

下面是有源码或在线检查依据的事实。修复方案在访谈确认后落实，不把建议标成已实现。

| 编号 | 表象和根源 | 影响 | 候选修复方向 |
|---|---|---|---|
| F01 | Database 表单复用通用条件，允许 not_in/contains/is_null/not_null/right_field；实际 statement 仅支持 eq/ne/gt/ge/lt/le/in，忽略 right_field | 可能发布后才报不支持，或比较了错误右值 | 统一能力声明、发布校验和执行语义；不支持项不能继续作为可选项 |
| F02 | 15种组件继承同一组 Data/Left data/Right data 输入 | 来源节点、Join、普通单输入节点均容易接出无效连线 | 按实际输入职责生成端口；参数依赖与数据集输入需明确区分 |
| F03 | Union 仍展示已禁用 deduplicate 与不生效 keys；Imaging 展示已禁用 quantity_field；Output 三个复数字段项未参与结果计算 | 看似配置成功，却被拒绝或没有效果 | 移除/迁移废弃入口，保留有效替代：Validate.identity、Imaging.evidence_field、Output.obligation |
| F04 | 条件必填未完整呈现：DB table/sql、File fields、Transform操作参数、Model openai.model、Imaging.evidence_field | 用户不知道必要配置，部分问题到运行才暴露 | 表单按模式显示必需项，发布前一致校验；默认值须与实际行为一致 |
| F05 | 提交任务界面只向参数编辑器传 type，遗漏 enum/description | 声明了枚举却仍要手写，提交后才发现非法值 | 根据已发布参数完整契约生成任务表单 |
| F06 | Filter/Validate 的 value、parameter、right_field 可以同时填写；条件执行会优先使用 right_field | 画布已有 insurance_paid 与自身比较的实际例子 | 明确互斥的右值来源，展示实际比较表达式，检查冲突配置 |
| F07 | 分页模式、转换操作、模型模式的无关配置多同时显示；子流程版本/输出仍为底层文本项 | 难分辨必需、条件必需与无效配置 | 收敛模式表单；子流程联动选择可独立排期，不阻塞本轮展开主链 |
| F08 | 旧方案要求日期窗口推导；现表达式没有相应日期函数 | 最新Q8已撤销此需求，不再是首轮阻塞 | 不新增日期窗口能力；另处理真实数据库时间绑定、时区元数据及时间比较适配，见核心路径复核 |
| F09 | 模板以 scope_confirmed 替代完整检查事实，清单和费用配置也未覆盖指定图 | 简化模板跑通无法证明指定图的主链跑通 | 建立与图逐项对应的受控模拟字段与正常样例，再验收缺口 |

源码依据：`catalog.py:19,101`、`connections.py:149`、`components.py:18`、`compiler.py:133,195,305`、`plugins.py:42`、`expressions.py:9,38`、`relational.py:253`、`sources.py:287,448`、`Schemes.tsx:210`、`SchemaForm.tsx:97`。

F08/F09 中还包含模板和接入契约缺口，不能全部归因于缺少新的节点类型。优先判断现有通用节点是否只需补配置、补适配或补通用能力。

## 6. 当前画布、活动版本与既有执行证据

本轮只读查看 `demo.consumables.v2`：

- 活动版本：v7，`4c90e368-927d-4712-8f40-81e43a1eb01a`；在线 inspect 无配置错误。
- 保存画布：`1dbd1737-dfd3-47aa-a93b-e68cd240440a`；检查失败。Catalog、Settlements 缺少字段依据，后续出现级联结构错误。
- 当前画布与活动版本并不相同。启动时保留了用户未发布修改，不能把发布版本校验成功说成当前画布也可发布。

画布保留的三处配置差异：

| 位置 | 当前画布 | 对主链的影响 |
|---|---|---|
| Facts.conditions[0] | value=true 的同时设置 right_field=insurance_paid | 实际变成 insurance_paid 与自身比较，false 也可能进入后续 |
| Settlements.detail_id | 类型从 text 改为 integer | 模拟真实响应 detail-hip/detail-knee 不满足整数声明 |
| Settlements.pagination | none 改为 page | 模拟接口不处理 page，可能重复读取同一批记录直到上限 |

这些是保存草稿的实际配置问题，不应把它们全部称为平台代码缺陷；F06 说明其中还有表单约束不足。本文不覆盖这些修改。

既有任务 `f3f3b3c9-1b1e-4883-844b-73d466596654` 创建于 2026-10-10，使用 v5：

| 正常比较记录 | 类别 | 数量（结算／观察） | 费用（结算／折算） |
|---|---|---|---|
| 膝关节 | 一致 | 1／1，一致 | 5000／5000，一致 |
| 髋关节 | 一致 | 2／1，不同 | 20000／10000，不同 |

该任务 completed，结果交代 accounted，但仍有两条 unresolved。baseline 的 6 次原始出现包含未知分类、医保事实缺失和范围外记录。现有 scenario 仅 baseline/adversarial；同院同日条件不能单独挑出纯正常膝样例。

**已有证据证明旧版本能处理其中一条正常膝记录；不证明 v7 已按本轮目标重新验收。** 数量/费用不同本身是合法业务结论，不等同技术失败。

证据：[既有验收结果](./evidence/refactoring-20261010/live-acceptance.json)、[启动迁移报告](../verification/.cache/startup-migrations/20261012T064414Z/report.json)、本轮在线只读查询。

## 7. 正常核心流程的验收拆分建议

画布实施仍须按[最终搭建方案](./CORE-FLOW-BUILD-PLAN.md)分阶段验证：

1. **能添加**：从业务方案的空白流程起步；文档中的每个实例均对应实际左侧组件。
2. **能配置**：逐项记录必需、条件必需、默认和可省配置；无效/废弃项不会误导用户；字段来源可追溯。
3. **能连线**：每条边记录来源端口、目标端口及期望字段；下游从正确端口下拉；参数绑定不冒充明细数据。
4. **能发布**：保存画布无配置错误；版本固定；不靠手改内部JSON或跳过校验来完成手工搭建验收。
5. **能执行**：使用确认的构造样例提交新任务；实际经过读取、筛选、检查、序列、影像、模拟观察、三项比较和持久输出。
6. **结果可核对**：从原始明细到核验单元、证据和各事项结果均能对应；预期数量、金额和差值有独立答案。模型模拟输出不由结算期待值直接生成。

每一阶段单独记录通过/未通过与证据。不用“进程在运行”“节点有输出”“任务 completed”代替业务结果正确。

本轮可以不展开异常处理演示，但保留正常结论成立需要的校验。后续另行验证合法不一致、缺失事实、来源不完整、接口失败等分支；不为了让正常样例通过而删除已有失败保护或结果责任。

## 8. 访谈决策树与已确认结论

此前字段绑定规则已经确认，本轮不重新讨论能否随意编造来源字段。

```text
指定0929业务图的正常核心流程验收（用户已确定）
├─ Q1 已确认：髋/膝各一组，三项结果全部一致
├─ Q2 已确认：从空白业务画布手工搭建并验收
├─ Q3 已确认：结算来自数据库，影像来自API；没有目录数据库
│  ├─ 附件：54条定义、50个不同字段；按用户要求准备一张模拟表
│  ├─ 三段影像API：已读取用户指定的Apipost公开文档
│  ├─ Q4 已更正：结算时间用UPDATE_TIME
│  │  ├─ Q4.1 已确认：按数量×单价比较费用，不加源金额列
│  │  └─ Q4.2 已确认：模拟统一按套计，单位约定在流程配置中
│  └─ Q5 已更正：HILIST_NAME名称范围筛选，当前不做分类映射
├─ Q6 历史决定：结算日期前7天至当天；已由最新Q8取代
├─ Q7 已确认：类别按同属髋/膝判断，不要求型号/全文相同
├─ Q8 最新决定：检查查询也使用监管提交的起止时间
└─ 上述选择确认后继续落实
   ├─ 受控样例：业务身份、分组口径、时间/部位与计数依据
   ├─ 图中字段与模拟接口契约、参数映射、字段发现方式
   ├─ 每个节点实例的必需配置、实际端口、字段输出与连线
   ├─ 必须修复的配置缺陷、模板缺口及可延期能力
   └─ 预期结果、逐阶段验收与后续异常分支入口
```

| 问题 | 已确认决定 | 说明 |
|---|---|---|
| Q1 | 首轮髋/膝各一组数据齐全、类别/数量/费用均一致 | 用户同意；合法不一致和异常分支后续验证 |
| Q2 | 从空白业务画布手工搭建、配置、发布和提交 | 用户同意；不能仅由脚本注入整张业务图作为验收 |
| Q3 | Database＋API；结算按附件准备，影像按指定接口文档模拟 | 用户选择混合接入，不采用首轮全API建议；目录无对应数据库 |
| Q4 | 结算时间直接使用UPDATE_TIME | 用户明确更正，取代旧图的SETL_TIME要求 |
| Q4.1 | 两侧数量分别乘同一PRIC，比较折算费用差 | 已确认；不增加原始明细金额列，不声称独立核对原账单 |
| Q4.2 | 两组模拟均按套计，PRIC按元/套 | 已确认；在流程配置中定义单位，不增加数据库单位列 |
| Q5 | 按HILIST_NAME模糊/范围匹配人工髋/膝关节 | 用户选择名称筛选，撤回编码映射和目录API候选方案 |
| Q6 | 历史约定：结算日期前7天至当天 | 已被Q8取代，不能继续作为当前搭建要求 |
| Q7 | 按髋/膝所属范围判断类别一致 | 首轮不比较具体型号或名称全文 |
| Q8 | 检查查询也使用监管提交的起止时间 | 保留chk_dt实际返回值；取消逐结算前7天窗口 |

最新Q8已取代Q6：检查查询与结算查询共用监管提交的起止时间，不再生成逐结算窗口；模拟仍明确北京时间。类别继续按Q7的髋/膝所属范围判断，首轮不核验型号。用户同时确认监管输入医院名字，以及影像地址按domain＋file_path拼接。当前已提出的业务口径问题均有答案，技术实现与验收仍未完成。最新原生输入口对照及必经源适配问题见[核心路径复核](./CORE-FLOW-CORE-PATH-REVIEW.md)。

用户另外授权的数据源准备已落实：50列原字段表、两条结算样例、连接及8091独立模拟API。最新逐实例配置、端口、字段和实施验收阶段见[最终搭建方案](./CORE-FLOW-BUILD-PLAN.md)。画布与必要节点能力尚未实施验收，不将数据源准备说成整图已通过。附件、接口及准备证据见[模拟数据源契约](./CORE-FLOW-DATA-CONTRACT.md)。
