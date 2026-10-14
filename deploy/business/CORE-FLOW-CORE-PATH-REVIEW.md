# 正常核心路径复核：时间、输入口与从0到1的验收

日期：2026-10-12。依据：用户本轮澄清、Q8回复、0929业务图、当前源码和只读实验。

**实施进度（2026-10-12）：已修改执行代码、配置表单和 Business 搜索入口；32 个节点的配置只读预检无错误。新画布正在通过界面搭建，尚未通过整图运行验收。** 下文保留实施前的问题清单和验收依据；最新实施证据见 [核心路径运行验收](CORE-FLOW-RUN-ACCEPTANCE.md)。已有数据源39项测试通过不能替代整图验收。

## 1. 最新有效决定

| 项目 | 本轮规则 | 与旧说明的关系 |
|---|---|---|
| 监管输入 | 医院名字、开始时间、结束时间；方案/规则仍通过方案选择确定 | 不要求监管知道医院编码，不增加检查窗口输入项 |
| 结算查询 | ORGAN_NAME匹配医院名字；UPDATE_TIME落在监管起止范围内 | 修正旧搭建表将hospital直接绑定ORGAN_CODE的错误 |
| 检查查询 | begin_time/end_time引用同一任务的start/end，另外带患者、医院、就诊等条件 | **最新Q8明确取代Q6，不再按结算向前推7天** |
| 实际检查时间 | 使用检查API返回的data[].chk_dt | 不计算、不覆盖为查询开始或结束时间 |
| 影像地址 | domain与file_path按供应方契约直接拼接 | 无需新增复杂URL组合规则；访问权限由供应方开通 |
| 首轮范围 | 髋、膝各一组正常住院样例，数据库＋API，独立模拟观察 | 不展开异常分支，不新增目录数据库或分类编码映射 |

此前“提交任务时的结算期间”就是监管提供的开始、结束时间。“结算范围”和“检查范围”仍分别约束不同记录的时间字段，但现在使用同一组边界，不再是两套配置。

首轮示例：

```text
医院名字：核心流程模拟医院
开始时间：2025-08-01 00:00:00
结束时间：2025-08-31 23:59:59
时区：北京时间（Asia/Shanghai）

Database：医院名字匹配，且 UPDATE_TIME 在上述范围内
  → 现有两条结算均为 2025-08-20 10:00:00

检查 API：begin_time/end_time 使用相同起止时间
  → 每条结算分别附带对应患者、医院、就诊条件
  → 实际返回 chk_dt = 2025-08-19 10:00:00
```

本轮模拟采用包含两端的比较。两侧查询范围相同，不代表两条实际时间必须相等，也不代表时间范围内任意检查均属于该结算。若任务只查8月20日，按照最新Q8就不会获得8月19日检查；不能暗中扩大范围。以上日期仅为受控样例，不修改已有结算或检查事实。

原图还单独规定住院检查早于结算。Q8只改变查询范围，未撤销该关联规则；首轮应检查 `chk_dt < UPDATE_TIME`，不是把“落在任务期间内”当作充分条件。两组现有样例符合该顺序。门诊规则暂不展开。

出处：原图业务页`request-map`及范围页`c1`；最新用户决定高于原图的旧窗口规则。API文档存档只声明begin_time/end_time和chk_dt为字符串，未充分说明真实服务的边界/时区；本轮模拟规则有明确实现，不能外推为真实供应方已经验证。

## 2. 为什么所有Business节点都画三个输入口

根因在 [BusinessComponent](../../src/backend/base/langflow/business/components.py)：公共基类统一定义了 `input_data`、`input_left`、`input_right`。各节点包装类没有按用途重定义，因此前端照常画出三口。这与业务catalog实际允许的输入不一致，部分无效线只能到发布校验时发现。

已检查运行中 `/api/v1/all` 模板，并结合前端 `isCanvasVisible`、`computeDisplayHandle` 核对。下面是新节点默认非工具模式下的**可见、可连接输入口**，不是配置字段总数：

| 原生节点 | 口数 | 输入 |
|---|---:|---|
| Chat Input、Webhook | 0 | 有可填配置，但默认没有输入连接点 |
| Chat Output | 1 | Inputs |
| If-Else | 2 | Text Input、Match Text |
| Parser | 2 | JSON or Table、Template；Template也可连接 |
| Language Model | 3 | Input、Language Model、System Message |
| Structured Output | 3 | Input Message、Language Model、Output Schema |
| LLM Selector | 3 | Input、Judge LLM、Language Models |

模式切换或字段显隐可能改变上述数量。原生三口节点本身正常；异常是不同职责的Business节点全部套用同一组口。

Business应按实际数据契约区分：

| Business节点 | 业务数据输入口 | 说明 |
|---|---|---|
| Parameters、Database、File | 0 | 来源或任务参数定义，不消费前序业务数据集 |
| Api、Subflow | 1：Data | 可选；Subflow是否需要数据由子契约决定 |
| Transform、Validate、Filter、Aggregate、Compare、Model、Imaging、Output | 1：Data | 消费一份输入数据集 |
| Join | 2：Left data、Right data | 两侧各一份数据 |
| Union | 1：Data | 同一个口接多条边，追加多份数据 |

Compare比较同表两列，两表应先Join。Union允许多条边不意味着需要多个独立口。

**参数依赖是兼容点：** 当前Parameters→Database的线被编译器当参数依赖处理，不是明细数据输入。整改不能直接删掉该线或把所有Data口统一去掉。应保留类名、kind和合法端口名，明确保留/迁移参数依赖；验证旧画布加载、保存、重新打开、发布及运行。仅CSS隐藏无法解决契约不一致。

## 3. 会直接阻止本轮运行的源适配问题

| 问题 | 已观察到的现象与根因 | 最小修复/适配及验收 |
|---|---|---|
| 数据库时间参数绑定 | 对真实TIMESTAMPTZ列比较任务时间字符串，SQLAlchemy将参数绑定成VARCHAR；PostgreSQL报 `timestamp with time zone >= character varying` | 按真实列类型绑定，并给任务时间明确时区；正确读取两条记录，测试时间边界 |
| 时间元数据丢失时区 | 反射列为TIMESTAMP(timezone=True)，metadata/表预览只保留str(type)=TIMESTAMP；实际结果是timestamp[us,tz=UTC]；执行器签名比较会误报结构变化 | 元数据、预览、编译签名与实际结果一致保留时区；验证发布后实际读取不误报 |
| 同一时间的传输格式 | 当前模拟API只接受北京时间YYYY-MM-DD HH:mm:ss；发送带+08:00的ISO字符串实际422，发送本地约定格式实际200 | 同一任务范围按目标类型编码。API发送约定文本，数据库按同一北京时间解析为带时区值；不能依赖数据库会话默认时区 |
| 地址字符串拼接 | 现有表达式domain+file_path编译为算术，DuckDB报VARCHAR+VARCHAR不支持；concat又被白名单拒绝 | 只开放受限concat即可，输出逐字等于domain＋file_path，保留签名参数；不扩展通用URL变换 |

数据库只读实测还确认：按列类型显式绑定ISO时间，或直接传带时区datetime，都能查询到两条样例。PG会话时区为UTC，故不能把没有时区的北京时间字符串交给数据库自行猜测。

现有SQL高级模式可以显式转换时间并通过SQL预览声明输出，是已有替代入口；它不等于表模式的上述问题已经修复。首轮无需新日期窗口节点，也不需要新增数据库列。

源文件：

- [connections.py](../../src/backend/base/langflow/business/connections.py)：metadata、preview、arrow_type、statement。
- [runtime.py](../../src/backend/base/langflow/business/runtime.py)：Database发布结构与运行结构比较。
- [core_flow_demo.py](../../src/backend/base/langflow/business/core_flow_demo.py)：查询日期解析、实际chk_dt过滤和模拟地址拼接。
- [expressions.py](../../src/backend/base/langflow/business/expressions.py)：算术及函数白名单。

## 4. 容易遗漏，但已有能力的正常链配置

| 项目 | 容易产生的误解/错误 | 本轮正确做法 |
|---|---|---|
| 医院名称 | 让监管额外查医院编码 | Database用ORGAN_NAME匹配hospital_name，记录中的ORGAN_CODE传给API。受控单医院无需新映射节点 |
| 参数与字段 | 把任务start/end填进上游字段下拉 | API请求编辑器选parameter模式；begin_time←start，end_time←end。真实字段才选field模式 |
| 日期事实比较 | 直接拿本地时间文本和UTC时间比较，或把任务范围内当作住院时序正确 | 保留原chk_dt；转为有明确时区的checked_at再与_context_UPDATE_TIME比较。本机cast已有，但不能隐含依赖主机时区 |
| 同节点派生依赖 | 同一Transform第二条规则引用第一条刚产生的列 | 目前表达式依据输入结构编译；需要前一步输出时拆成下一个Transform。例如concat补+08:00，再cast成datetime |
| 字段下拉与实际值 | 知道字段名就以为已经有一行可预览数据 | 元数据/契约可在整图未运行时提供结构；显式接口预览需要请求样例。不会自动执行全部上游来取值 |
| API字段依据 | 修改请求之后沿用旧样本/旧契约绑定 | 使用当前请求的字段依据；只声明本轮用到、有出处的响应字段。不凭空加cardno响应字段 |
| 患者与就诊 | 把HIS的PSN_NO等同云影像system_patient_id；同患者就认为同次就诊 | name/cardno取PSN_NAME/CERTNO，另外约束医院、就诊类型/编号；响应再次核对相应事实 |
| 跨API关联 | 末级_request_row_id当成最初结算行号 | 复制_business_row_id到unit_row_id，API各级context_fields透传；识别_context_前缀并恢复 |
| 下一接口主键 | study_primary_id、series_id与DICOM UID混用 | 按三份接口契约逐级传递相应请求ID；DICOM UID另用于影像身份 |
| 响应与完整性 | HTTP200就当业务成功、默认无分页就当取全 | items_path=data；核对code=200/error.error_code=0；pagination=none仅配合受控模拟完整性basis，不宣称真实全量 |
| 影像展开 | 一条1套结算有两张图，求和得到2套 | 仅按unit_row_id collect(file_ref)为清单，再与保留的结算基准one_to_one Join |
| Join输出 | 仍引用关联前旧字段名 | 从实际输出选择left_/right_前缀字段，再显式恢复后续所需名称 |
| 模型独立性 | 把数据库CNT当期待数量发给模型，再原样回传 | Imaging不配置已禁用quantity_field；使用独立模拟观察。证据清单必须配置evidence_field |
| 类别与金额 | 名称不完全相等就判错，或拿结算总额当耗材明细费用 | 按髋/膝范围对齐；两侧数量按套，分别乘同一PRIC。精确型号和原账单金额不在本轮范围 |
| 结果交代 | 任务completed或只显示一条正确结果就算成功 | 主Output声明来源、身份、单元及类别/数量/费用三个事项；两条明细均有持久结果、证据和版本 |

已有能力依据：`sources.py`的bindings/context_fields与响应校验；`relational.py`的cast/collect/Join/Compare；`coverage.py`的结果责任；前端RequestBodyEditor、字段发现及SchemaForm。

医院别名/多院区解析曾存在于旧verification路径，但当前Business不会自动调用；本轮精确名称匹配可完成受控正常路径，不能冒称已覆盖正式医院映射。

## 5. 表单整改的边界

本轮直接涉及：正确端口呈现与参数依赖兼容；条件右值只选常量、参数或另一个字段之一；源数据库只提供实际支持的条件；Imaging证据必填；时间类型和地址表达式能配置并发布。

现有Filter可做HILIST_NAME contains，不需要先给Database增加contains。Union首轮只追加，不勾已禁用的deduplicate，也不填无效keys；Output用columns与obligation，不依赖无效的key_fields/reason_fields/evidence_fields。上述“正确配置能避开的误导项”应清楚标出，但不能把所有表单重构都作为执行首轮的前置条件。

File、通用Model、Subflow、医院别名、多价格/多明细归并、真实分页、门诊和异常分支的完整整改暂不纳入本轮。通用绝对URL处理、签名解析和日期函数库也不需要新增。

## 6. 从0到1的最小验收顺序

1. **修复必经适配**：时间绑定、时间类型保真、传输格式对齐和受限字符串拼接；用实际两条源记录验证。住院时序用已有cast与条件能力，不新增业务时间窗口。
2. **检查画布可配置性**：按真实职责呈现输入口，保留参数依赖兼容；字段、参数和条件右值必须可准确选择。验收保存/重新打开，避免旧配置残留。
3. **从空白Business方案搭建**：Parameters → Database → Validate/Filter → 保留结算基准 → 检查API → 时序/身份/部位检查 → 序列API → 影像API → 拼地址 → Aggregate → Join结算基准 → Imaging → 比较前提校验 → 类别/数量/金额 → Output。具体实例见搭建方案；不靠脚本注入整图替代画布验收。
4. **发布、启用并实际提交任务**：使用医院名字和上述整月起止时间；记录新方案、flow、release、task标识，验证调用新8091接口及实际数据库。
5. **核对数据和持久结果**：不仅看流程是否completed，还逐阶段核对下面的独立预期。

| 阶段 | 预期 |
|---|---|
| 结算 | 2条：人工髋/膝各1条，医院及UPDATE_TIME在任务范围内 |
| 检查 | 共2条；保留实际chk_dt，患者、医院、就诊、模态、部位及时序均匹配 |
| 序列/影像 | 2条序列、4张模拟影像引用 |
| 证据/观察 | 2份清单，每份2张；2份独立观察，均1套 |
| 最终结果 | 2行、共6个事项一致；髋10000元、膝5000元，两侧数量和金额差值均0 |
| 可追溯 | 两条来源均交代，没有静默丢行；身份、证据、发布版本与持久结果可查 |

当前已经具备数据库两条样例、三段模拟API和独立观察接口；上述第1—5步仍没有完成新的整体验收。真实DICOM下载、模型识别准确率和正式供应方权限联调留在后续范围，不把本轮模拟通过解释为它们已通过。

关联文档：[搭建方案](./CORE-FLOW-BUILD-PLAN.md)、[数据契约](./CORE-FLOW-DATA-CONTRACT.md)、[节点审计与决策记录](./CORE-FLOW-NODE-AUDIT.md)。历史准备/测试报告保留原状，不回写为本轮执行证据。
