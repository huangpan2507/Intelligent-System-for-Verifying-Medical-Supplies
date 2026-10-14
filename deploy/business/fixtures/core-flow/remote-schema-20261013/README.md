# 远端检查与序列表结构快照

采集时间：2026-10-13 14:58（北京时间）。

数据源：用户指定的 `10.159.5.92:9030 / mirror_db`。结构采集阶段只读取服务器版本、`SHOW FULL TABLES`、`SHOW FULL COLUMNS`、`SHOW KEYS` 和 `SHOW CREATE TABLE`，未查询业务记录，未修改远端对象。文件不含连接口令或患者记录。后续经用户明确批准的小样本核对单独记录在文末。

WSL 直连仍在握手阶段失败；通过 Windows 本机已有 Python 3.10、复用现有纯 Python PyMySQL 包成功认证并取得结构，没有安装软件。`VERSION()` 返回兼容版本 `5.7.99`；`@@version_comment` 明确返回 `Doris version doris-2.1.10-rc01-33df5ba180`。

## 文件内容

- `schema-report.json`：完整列元数据（包括类型、空值约束和注释）、辅助索引、对象类型和版本证据。
- 四个同名 `.sql`：`SHOW CREATE TABLE` 返回的完整结构。
- 结构采集阶段没有真实编号样本，因此这些结构文件不能证明 `link_id` / `global_id` 的取值格式。

## 已证实的字段和关系

| 对象 | 列数 | Doris UNIQUE KEY | 本轮关注字段 |
| --- | --- | --- | --- |
| `yb_emr_inspection_info_record_s` | 93 | `organ_code, system_id, ris_study_id` | 三个键均为非空 `varchar(255)`；`rpt_no` 为可空 `text`，注释“检查申请单编号”；`chk_dt` 为可空 `bigint`，注释“检查日期时间”；没有 `link_id` 或 `global_id` |
| `yb_dp_series_info_s` | 162 | `organ_code, system_id, pacs_series_id` | 三个键均为非空 `varchar(1024)`；`ris_study_id` 为可空 `varchar(1024)`；没有 `link_id` 或 `global_id` |
| `yb_emr_inspection_info_record_v` | 46 | `organ_code, system_id, ris_study_id` | `link_id` 为可空 `varchar(255)`；`chk_dt` 为 `datetimev2(0)`；`rpt_no` 注释为“报告单号”，与 `_s` 的注释不同 |
| `yb_dp_series_info_v` | 175 | `organ_code, system_id, pacs_series_id` | `link_id` 为可空 `varchar(512)`；`global_id` 为可空 `text`；`ris_study_id` 为可空 `varchar(512)` |

所有字段名均以快照中的小写为准。以上四个对象全部是 `BASE TABLE`；`_v` 后缀不代表数据库视图，不能通过读取其 DDL 推导编号的生成表达式。`SHOW KEYS` 返回辅助索引，Doris 的唯一键须以 `SHOW CREATE TABLE` 中的 `UNIQUE KEY` 为准。

本次 `SHOW FULL TABLES` 没有发现名为 `INSPECTION_INFO_RECORD` 或 `SERIES_INFO` 的对象（忽略大小写比较）。本地拟建表名称不属于已证实存在的远端对象。

## 仍未由结构证实

1. `link_id` / `global_id` 的实际格式、唯一性范围和生成规则；注释仅为字段名称。
2. `_s.chk_dt` 的 `bigint` 值采用秒、毫秒或其他编码；元数据没有单位说明。
3. `rpt_no` 没有源表唯一键约束，因此不能仅凭 DDL 声称每个申请单必然只对应一条检查。
4. 源数据库为 Doris，不能直接把 `datetimev2`、存储属性以及较长的复合唯一键原样用于本地 MySQL。

这些未知项应作为待确认的契约记录，不能以模拟值冒充远端事实。

## Q12 授权后的有限样本核对

2026-10-13 15:14（北京时间），用户明确批准每张相关表最多三条、仅关联编号及检查时间的内存核对。每表仅执行一次指定字段的 `LIMIT 3` 查询；没有使用 `COUNT`、没有扩大抽样、没有读取姓名、证件、联系方式或影像。真实编号、散列值和检查时间未输出或保存。

新增 `identifier-format-report.json` 仅保存格式、长度、匹配布尔值和取样条数。历史 `schema-report.json` 中 `business_rows_read: 0` 仍表示此前的纯结构采集阶段，没有改写。

| 对象 | 实际样本数 | 脱敏核对结果 |
| --- | --- | --- |
| `yb_emr_inspection_info_record_s` | 3 | `chk_dt` 均为 13 位整数；在候选编码检查中与 Unix 毫秒相符。这支持毫秒时间戳推断，不代表验证了全部记录或供应方契约。 |
| `yb_emr_inspection_info_record_v` | 3 | `chk_dt` 均由驱动返回日期时间对象；`link_id` 长度为 6、6、32，仅最后一个为 32 位十六进制；三者均不等于下述新模拟规则计算结果。 |
| `yb_dp_series_info_s` | 0 | 此次查询没有返回记录，无法对其编号进行样本验证。 |
| `yb_dp_series_info_v` | 3 | `link_id` 均为 35 字符且非 32 位十六进制；三者均不等于下述新模拟规则计算结果；`global_id` 均为 NULL，不能证明其格式或生成规则。 |

用于本次比较的公式是 `MD5(UTF8(organ_code + '_' + system_id + '_' + ris_study_id))`。用户已明确要求新建的本地模拟表采用该公式；此次有限远端样本不支持声称既有远端数据也统一遵守这一公式。`global_id` 的来源规则仍未得到样本验证。
