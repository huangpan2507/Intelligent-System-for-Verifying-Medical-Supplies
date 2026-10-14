# 本地模拟检查与序列数据源

2026-10-14：原画布已使用这两张 MySQL 表完成正常链路运行，膝关节样例为非住院标记1；见[完整验收](../../../CORE-CLASSIFICATION-ACCEPTANCE.md)。

2026-10-13 已创建并通过数据源验证。这里的全部业务记录均为合成记录，没有复制远端患者或编号样本。

## 已建立的资源

| 数据源 | 表 | 字段数 | 样例数 |
|---|---|---:|---:|
| PostgreSQL `127.0.0.1:55434/business_demo` | `public.core_flow_settlement_v1` | 51 | 2 |
| MySQL `127.0.0.1:13306/business_demo` | `INSPECTION_INFO_RECORD` | 94 | 2 |
| 同一 MySQL | `SERIES_INFO` | 164 | 2 |

平台连接为 **模拟检查与序列 MySQL (核心流程)**，ID `fb22b9dd-11b7-4650-b86d-78332de3e2ec`。在 Business Database 的 Connection 中选择此连接，然后在 Table 中选择上述任一 MySQL 表，即可从真实元数据中下拉字段；不需要先运行 workflow。

结算仍使用原连接 **模拟结算 PostgreSQL（核心流程）**，ID `537d8c03-3c9a-4c25-8a8e-d66cfc2b187a`。新增 `SYSTEM_ID VARCHAR(16) NOT NULL`，并为两条样例补齐 `RPT_NO`；`DATA_SOURCE` 仍为 `MOCK-HIS01`，检查所属系统为 `MOCK-RIS01`。

## 标识与时间

两张 MySQL 表都采用以下本地模拟契约：

```sql
link_id = MD5(CONCAT(organ_code, '_', system_id, '_', ris_study_id))
```

输入按 UTF-8 编码、保留原值及大小写，不额外去空格；输出为 32 位小写十六进制摘要，列类型为用户指定的 `VARCHAR(512) NOT NULL`。MD5 在这里用于生成关联标识。

同一检查在检查表和序列表具有相同 `link_id`；一个检查存在多个序列时，这些序列共享该值，因此序列表不能把 `link_id` 设为唯一键。

序列表新增 `global_id VARCHAR(512)`，首轮为 `MOCK-SERIES-HIP`、`MOCK-SERIES-KNEE`，与保留的 8091 模拟影像 API 完全对应。它是序列级标识，不由检查级 `link_id` 直接替代。用户没有指定其生成算法，远端有限样本也均为空；本轮沿用现有模拟服务认可的编号，不冒充真实服务的生成规则。

检查 `chk_dt` 本地类型为 `DATETIME`，以北京时间解释，样例值 `2025-08-19 10:00:00`。用户给出的 `2026-09-01 09:01:23` 是格式示例，本轮没有因此改变已确认的 2025 年 8 月样例与任务范围。查询参数仍为 `2025-08-01 00:00:00` 至 `2025-08-31 23:59:59`，结算时间仍为 `UPDATE_TIME`。

## 关联配置

| 阶段 | 左侧字段 | 右侧字段 |
|---|---|---|
| 结算 → 检查 | `ORGAN_CODE`、`SYSTEM_ID`、`RPT_NO` | `organ_code`、`system_id`、`rpt_no` |
| 检查 → 序列 | `organ_code`、`system_id`、`ris_study_id` | 同名三个字段 |
| 序列 → 影像 API | `global_id` | GET `/api/v2/storage/dicom/sop-instance-uid` 的 `series_id` 参数 |

影像地址仍为 `domain + file_path`。旧检查 API 和序列 API 在服务中保留供旧方案使用，新数据源链路不调用这两段 API。

## 与 Doris 源结构的区别

- 保留检查 `_s` 的全部 93 个列名及序列 `_s` 的全部 162 个列名，再补充用户指定的列。字段注释、空值属性及适用默认值尽量随原结构保留。
- 检查源 `chk_dt BIGINT` 按用户本次要求改为本地 `DATETIME`。有限远端样本呈 13 位整数，仅支持“毫秒时间戳候选”的判断；没有把这一推断当作已确认的生产时间协议。
- Doris `datetimev2(n)` 转为 MySQL `DATETIME(n)`。其余 BIGINT 时间列保留源类型，本轮不填充或用于核心时间筛选。
- 序列表 156 个 `VARCHAR(1024)` 转为 `TEXT`，每列保留 `CHAR_LENGTH <= 1024` 检查，避免 MySQL 行定义过宽；不截断字段值。完整转换清单见 `type-adaptations.json`。
- 检查表保留医院＋系统＋检查号的复合主键。序列表在本地用 `global_id` 作主键；源医院＋系统＋`pacs_series_id` 的完整复合键没有机械照搬为超长 MySQL 索引，也没有用前缀索引代替。模拟数据仍遵循该序列身份，后续画布应以完整字段配置身份验证。
- 本地使用 `utf8mb4_bin`，并明确这只是模拟库的比较规则；不宣称与 Doris 全部排序和字符比较语义完全等价。
- 不复制 Doris 引擎、分桶和存储属性。此处是能被 Business Database 实际读取的模拟数据源，不是 Doris 完整物理镜像。

## 验证证据与复用

`preparation-report.json` 记录了 PostgreSQL 结算与 MySQL 检查/序列的实际关联，以及使用数据库 `global_id` 发起的真实 HTTP 调用：2 条结算、2 组检查与序列、4 条模拟影像引用；数据库 MD5 表达式校验通过。

`platform-schema.json` 是平台字段发现接口返回的 51／94／164 个字段。`rows.json` 是本地合成数据，两个 SQL 文件为可审阅的本地建表语句。

```bash
# 只生成 DDL 和合成记录，不连接数据库
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python scripts/business/prepare_core_database_sources.py

# 在现有本地结算表和服务上建表、补齐数据、登记连接并验证
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python scripts/business/prepare_core_database_sources.py --apply
```

脚本复用本地私有凭据文件，不含远端口令；已有目标行被修改时会报错并保留原值，不清空表。原始附件字段字典和旧验收报告保持为历史记录。

本轮已完成数据源准备和关联验证，**没有执行或验收整张新 Business 画布**。旧画布及 32 节点脚本仍需按新来源和真实字段类型改造、发布并运行。
