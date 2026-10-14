# 正常核心流程：检查、序列改为模拟数据库

> 2026-10-14 更新：原画布已完成数据库来源迁移及正常核心路径验收，见[规则＋真实文本模型验收](./CORE-CLASSIFICATION-ACCEPTANCE.md)。下文为2026-10-13建表阶段记录。

日期：2026-10-13。阶段状态：Q9—Q12 已确认，已按用户最新规则建立本地模拟表、补齐结算字段，并通过数据库关联与影像 API 验证。整张新画布尚未改造和验收。最新资源、配置和验证证据见[模拟数据源使用说明](./fixtures/core-flow/database-sources/README.md)。

本文件记录用户对原三段 API 方案的变更。它取代旧方案中“检查列表 API → 序列列表 API”的取数方式；未更改的业务规则继续有效。旧画布尚未完成整图运行验收，不能沿用旧配置预检结果证明新链路已通过。

## 已确认的变更

| 对象 | 最新要求 |
|---|---|
| 结算表 | 继续使用现有模拟 PostgreSQL 的 `business_demo.public.core_flow_settlement_v1`，新增 `SYSTEM_ID`：必填字符串，最大 16 字符；保留原 `DATA_SOURCE` |
| 检查表 | 参考测试库 `mirror_db.yb_emr_inspection_info_record_s`，创建模拟表 `INSPECTION_INFO_RECORD`，要求包含 `link_id VARCHAR(512)` |
| 序列表 | 参考测试库 `mirror_db.yb_dp_series_info_s`，创建模拟表 `SERIES_INFO`，新增 `link_id VARCHAR(512)`、`global_id VARCHAR(512)`；用户在 Q12 回复中明确改为 VARCHAR(512)，取代 Q11 的 TEXT 决定 |
| 新表位置 | Q9 已确认：本地模拟 MySQL `127.0.0.1:13306/business_demo`。远端测试库只作为结构参考 |
| 第一段关联 | Q10 已确认：医院＋检查所属 `SYSTEM_ID`＋`RPT_NO`，将结算关联至检查记录；源列名按真实结构映射 |
| 第二段关联 | Q10 已确认：医院＋检查所属 `SYSTEM_ID`＋`ris_study_id`，将检查关联至序列；源列名按真实结构映射 |
| 第三段关联 | 将序列表 `global_id` 绑定为影像列表 API 的请求参数 `series_id` |
| 检查编号映射 | 用户明确 `study_primary_id = link_id`，两表均按 `MD5(organ_code + '_' + system_id + '_' + ris_study_id)` 生成；同一检查的两表 link_id 相同，序列间可以共享该值 |
| 检查时间 | 用户明确本地按 `YYYY-MM-DD HH:mm:ss` 使用，采用 MySQL DATETIME，按 Asia/Shanghai 解释；不沿用源 `_s` 的 BIGINT 作为本地 chk_dt 类型 |
| 影像列表 | 保留影像列表 API；影像地址仍为 `domain + file_path` |

这里的 `INSPECTION_INFO_RECORD`、`SERIES_INFO` 是两个表名；两表建在同一个本地模拟数据库内，不新建两个数据库实例。不把远端患者记录复制为模拟数据。

## 建表前的本地只读核查结果

2026-10-13 直接查询现有数据库得到：

- 结算表已有 `RPT_NO`，允许空值；髋、膝两条模拟记录的值均为 `NULL`。因此除了加列，还必须补齐两条结算与检查的匹配申请单编号。
- 结算表没有 `SYSTEM_ID`，已有 `DATA_SOURCE`；两条记录的 `DATA_SOURCE` 都是 `MOCK-HIS01`。不能以已有字段为理由省略用户要求的新列，也不能未经依据把两个系统标识视为同义。
- 结算表 `UPDATE_TIME` 为带时区时间戳，`ORGAN_CODE` 必填。
- 本地 MySQL 目前只有 `orders`，尚不存在两个目标表。
- 当前模拟服务使用 `MOCK-STUDY-HIP/KNEE` 与 `MOCK-SERIES-HIP/KNEE`。新表编号需要与保留的模拟影像接口对齐；新造一个不被接口识别的 `global_id` 不会自动获得影像。

## 远端只读核查状态

首次核查目标为 `10.159.5.92:9030` 下的两张源表，仅查询结构作为参考。当时普通环境与提权环境各一次 PyMySQL 连接均返回错误 2013；独立 TCP 探测可连接，但约 5 秒后关闭，未收到 MySQL greeting，当时未进入认证和 `SHOW / DESCRIBE` 阶段，不能认定是口令错误。

首次核查时，本机 Windows PowerShell 的单次独立探测同样能建立 TCP 连接，但约 5 秒内没有收到 MySQL greeting，最终读取超时。当时未能证明问题仅发生在 WSL。

用户确认 Q10/Q11 并要求重试后，WSL 的 PyMySQL 连接仍返回 2013；Windows 本机本轮探测则在约 0.18 秒收到 78 字节 MySQL protocol 10 greeting。随后使用 Windows 已有 Python 3.10、复用现有 PyMySQL 成功认证；没有安装软件。`VERSION()` 为兼容版本 `5.7.99`，`@@version_comment` 明确为 `Doris version doris-2.1.10-rc01-33df5ba180`。实际服务为 Apache Doris，支持 MySQL 协议，不是本地模拟库采用的 MySQL 引擎。

2026-10-13 14:58（北京时间）已取得两张 `_s` 表及对应 `_v` 表的完整 DDL、列元数据和键定义，见[只读结构快照](./fixtures/core-flow/remote-schema-20261013/README.md)。无需用户再导出以下结构：

```sql
SHOW CREATE TABLE mirror_db.yb_emr_inspection_info_record_s;
SHOW CREATE TABLE mirror_db.yb_dp_series_info_s;
```

结构采集阶段没有读取业务记录或编号样本；后续仅在用户明确批准 Q12 后进行了下述限定样本核对，始终未修改远端表。结构快照不包含连接口令或患者记录。

### 源结构与本地字段映射

| 对象 | 已核实事实 | 对模拟方案的影响 |
|---|---|---|
| `yb_emr_inspection_info_record_s` | 93 列；`organ_code/system_id/ris_study_id` 为非空 `VARCHAR(255)`，三者构成 Doris UNIQUE KEY；`rpt_no` 为 TEXT，注释为检查申请单编号；`chk_dt` 为 BIGINT | 以此表为检查表依据，加 `link_id VARCHAR(512)` 后已建成 94 列；保持源字段小写 |
| `yb_dp_series_info_s` | 162 列；`organ_code/system_id/pacs_series_id` 为非空 `VARCHAR(1024)`，三者构成 Doris UNIQUE KEY；`ris_study_id` 可空；无 `link_id/global_id` | 以此表为序列表依据，增加两列后已建成 164 列；检查关联用 `ris_study_id`，序列身份用 `pacs_series_id`，不能混用 |
| `yb_emr_inspection_info_record_v` | 46 列；有 `link_id VARCHAR(255)`；`chk_dt` 为日期时间；`rpt_no` 注释为报告单号 | 仅用于核对编号及时间表示；不以它替换用户指定的 `_s` 源结构，不将报告单号注释套用到申请单编号 |
| `yb_dp_series_info_v` | 175 列；有 `link_id VARCHAR(512)` 和 `global_id TEXT` | 证明这些字段在测试环境确实存在，但不能仅凭类型和列名确定值的构造规则 |

四个对象均为 `BASE TABLE`，`_v` 后缀不代表数据库视图，没有可读取的编号生成表达式。源库未发现名为 `INSPECTION_INFO_RECORD`、`SERIES_INFO` 的对象；这两个名称用于本次本地新建表。

结算大写字段与源小写字段的明确映射为：`ORGAN_CODE → organ_code`、`SYSTEM_ID → system_id`、`RPT_NO → rpt_no`；第二段两侧使用 `organ_code/system_id/ris_study_id`。结算表保留 `DATA_SOURCE` 作为结算明细身份的一部分。

### 已明确的类型适配及待改造的旧配置

- 源 `_s.chk_dt` 为 BIGINT，有限样本呈 13 位整数；用户已明确本地模拟按日期时间形式使用，因此本地改为 DATETIME。旧 API 的字符串拼接配置仍需按真实 DATETIME 类型调整；实际检查时间保持为记录中的事实，不从查询范围推算。
- 检查 `op_em_hp_ex_mark` 为 INT，而现有结算 `OP_EM_MARK` 为文本。比较前需显式统一类型，不能把类型差异当作就诊类别不一致。
- `_s` 有 `upload_status`，没有旧 API 的 `is_upload`。两者码值含义尚无依据，不能直接把 `is_upload=1` 改名为 `upload_status=1`。核心链路仍需以保留的影像 API 返回及清单验证确认影像依据。
- 源唯一键不包括 `rpt_no`，不能仅凭 DDL 认定一个申请单只能关联一个检查。首轮仍构造一条结算对应一个检查的两组正常样例；不以样例关系冒充生产唯一性保证。
- Doris 的 ENGINE、分桶、PROPERTIES、倒排索引等不复制到 MySQL。序列表 156 个 `VARCHAR(1024)` 已转换为 TEXT 并保留字符长度检查；本地以 global_id 为主键，不通过截断编号或前缀唯一索引冒充完整源复合键唯一性。实际 MySQL 8.4 建表已成功，转换清单已保存。

### Q12：编号及时间表示核对

DDL 不能证明 `link_id/global_id` 的取值格式，也不能证明 `chk_dt` 整数的时间单位。此前自动审批拒绝了最多 5 条编号格式样本读取，理由是超过当时明确的结构核查授权、可能涉及敏感业务数据；已改用纯元数据方式完成上述结构核查，没有执行样本查询。

用户已明确批准每张相关表最多 3 条的限定核对，现已完成，每表仅一次 LIMIT 3。只核对医院/系统/检查/序列编号、`link_id/global_id/chk_dt`，未保存原值，未查询姓名、证件、联系方式或影像内容；证据见[脱敏格式报告](./fixtures/core-flow/remote-schema-20261013/identifier-format-report.json)。

- 检查 `_s` 的 3 条 chk_dt 均为 13 位整数，支持 Unix 毫秒候选解释；检查 `_v` 的 3 条均为日期时间对象。
- 检查 `_v` 的 link_id 长度为 6、6、32；序列 `_v` 的 3 条均为 35 位。上述样本均不匹配本次指定的下划线连接 MD5 规则。
- 序列 `_s` 本次返回 0 行；序列 `_v` 的 3 条 global_id 均为空，无法验证其生成算法。

因此本地以用户本次明确给定的规则为准：UTF-8 输入、下划线连接、32 位小写十六进制 MD5 摘要；它是本地模拟契约，不声称远端数据统一遵守。global_id 用 VARCHAR(512) 存储现有模拟影像 API 可识别的序列编号，避免用检查级 link_id 替代序列级标识。

## 保留的业务规则

- 监管输入仍是医院名字、开始时间、结束时间。结算记录按 `ORGAN_NAME` 与 `UPDATE_TIME` 筛选。
- Q8 继续有效：检查范围使用同一组监管起止时间，不恢复“结算前 7 天”。实际检查时间读取本地检查表已建立的 `chk_dt DATETIME`。
- `RPT_NO` 提供新的直接关联依据，不以姓名、日期相近替代该关联。
- 髋、膝类别仍从 `HILIST_NAME` 匹配；数量按套，价格按元/套，独立观察数量与结算数量分别折算金额。
- 首轮仍以髋、膝各一组正常模拟验证核心流程，影像引用及观察结果保留明确的模拟性质。

## 拟采用的节点结构

```text
Request ──→ Database：结算 → 正常结算/目标耗材筛选 ──┐
        └─→ Database：检查 → 时间/必要条件筛选 ───────┴→ Join：申请单关联 ─┐
            Database：序列 ───────────────────────────────────────────┴→ Join：检查与序列关联
              → API：影像列表（series_id ← global_id）
              → Transform：domain + file_path
              → 按核验单元收集影像清单 → 独立模拟观察 → 类别/数量/金额比较 → Output
```

现有 Business Database 在执行时读取任务参数，并不会像 API 节点一样逐条把上游记录作为查询参数。因此不能只把两个 API 节点换成 Database 并沿用原串联线；本轮拟使用多个 Database 数据集与 Join 节点完成关联。有限模拟表的读取范围明确记录，不能将读取全部模拟记录的做法称为生产大表查询方案。

必要配置须包含数据源真实字段下拉、关联键、关联基数和同名字段处理。需保留结算明细/核验单元身份，避免检查或序列展开导致 `CNT` 和金额重复累计。

## 已完成的决定与剩余工作

- 数据源位置：已解决（Q9，本地模拟 MySQL）。
- 源结构：已通过 Windows 认证并取得四张表的结构，字段名和关联字段已核实；Q12 限定样本核对已完成。
- 数据源：已新增两张模拟表和一条平台连接，补齐结算 SYSTEM_ID/RPT_NO；保留源检查 93 列、序列 162 列，新表分别为 94 列、164 列，结算表为 51 列。
- Q10 关联范围：用户已确认第一段用医院＋检查所属系统＋申请单编号，第二段用医院＋检查所属系统＋检查编号。结算 `SYSTEM_ID` 表示对应检查所属系统，不覆盖结算来源 `DATA_SOURCE`；源字段映射须有依据。
- Q11 后续更正：用户在 Q12 回复中明确改为 global_id VARCHAR(512)，已按最新要求建表；两表 link_id 均为 VARCHAR(512)。
- 数据源验证：平台字段发现、两段实际关联、SQL MD5 校验和影像 API 均通过：2 条结算、2 组检查/序列、4 条影像引用。脚本重复执行通过，未新增重复记录或连接。
- 新画布验收：原 32 节点脚本、检查点与验收清单仍需按新结构修订，尚未发布或执行整张新画布，未据此宣称 2 条最终比较结果已产生。

## 本轮实施边界

按用户显式调用的 grilling 技能先完成结构与口径核对。用户确认 Q9—Q12 并明确再次要求本地模拟表后，本轮完成其已授权的数据源准备；远端仅执行元数据与限定样本只读查询。本地脚本和可审阅 DDL、合成记录、平台字段和验证报告均已落盘。

整图最终验收目标仍是：2 条结算、2 条关联检查、2 条序列、4 条影像引用、2 份完整清单、2 条独立观察、2 条结果；类别、数量、金额共 6 项一致。其中本轮已核实至影像列表取回阶段；整图执行及最终比较仍未验收。
