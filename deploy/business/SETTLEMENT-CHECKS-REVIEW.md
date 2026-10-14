# SettlementChecks：质量检查、业务范围与重复记录复核

日期：2026-10-13。对象：`髋膝关节正常核心流程（数据库＋API）`，画布 ID `e55b03b0-7c7f-420b-b720-33b1a4cf5559`。

> 2026-10-14：用户取消住院限制，并讨论业务条件前移数据库及名称语义分类。最新需求与待确认项见[结算范围复核](./SETTLEMENT-SCOPE-REVIEW.md)。本文保留此前实施和验收事实，不代表新范围已落地。

本次采用 grill-with-docs：质量/范围边界、码表，以及用户已确认的 Q16 两口方案均已落实。本文记录本次节点改造，不是整张髋膝画布运行验收报告。

## 1. 已实施 Q16：两个输出，Issues 区分错误与提示

当前配置了 Identity：`ORGAN_CODE + DATA_SOURCE + SETL_FEE_LIST_ID`。相同身份的记录还会比较全部原始业务事实。

| 输入情况 | 当前去向 | 业务效果 |
|---|---|---|
| 一条质量合格的独立明细 | Valid | 正常继续 |
| 同一明细重复出现，全部原始事实一致且质量合格 | 一条代表记录进入 Valid，其余进入 Issues，分类为已合并重复提示 | 后续只计一次，每次原始出现仍可追溯，不阻断、不计入待处理 |
| 同一明细的原始事实不同，例如数量分别为 1 和 2 | Issues | 不任意挑一条作为正确事实 |
| 必需属性为空、数量不符合配置等 | Issues | 保留质量问题原因 |

普通 Unique 配置会将重复键整组判为问题，不能替代“完全重复合并、事实冲突隔离”。未配置 Identity 时，不自动识别或合并重复记录。

用户此前已在 [D04](./REFACTORING-PLAN.md) 确认“完全重复只算一次，原始出现可追溯”；该决定没有要求必须用第三个端口展示。

本核心来源是单表读取，模拟表主键正好是上述三列，因此正常两条样例没有重复记录。通用节点仍可处理多来源、分页重叠等重复输入，但不再要求使用者理解或连接第三口。

具体实现：校验输出增加 `_issue_severity`，错误为 `error`，已合并重复为 `info`，Valid 行为空值。重复提示通过 `_identity_status=exact_duplicate` 保留原因，`_issue_reason` 留空；该字段继续只承载阻断理由。重复行如果自身也不满足质量条件，仍属于 `error`，不能仅凭“重复”降低等级。任务结果页显示中文分类“数据错误”“已合并的重复记录（提示）”，七种语言同步提供翻译。

执行器只把 Issues 的错误行传播为依赖阻断；Valid 的代表明细仍关联全部相同的原始出现。覆盖统计读取两口，任务待处理计数排除提示。新跨库和耗材模板的既有错误分支经过 Filter 分流，避免把结算或影像重复提示记成错误/未比较。设计理由见 [ADR-0002](../../docs/adr/0002-validation-issues-include-duplicate-notices.md)。

旧画布和旧发布包的 Issues 原本仅包含错误，不能直接改为接收混合结果。迁移仅识别明确的旧组件源码，刷新为两口，并在存在旧消费者时插入一个既有 Filter：`_issue_severity=info` 的 matched 承接旧 Duplicates，下游 unmatched 承接旧 Issues；覆盖声明中的端口引用同时迁移。没有消费者的节点只刷新输出定义。未知改写的源码仍拒绝发布，历史发布包保持不可变，重新发布产生新版本。

迁移脚本为 [migrate_validate_outputs.py](../../scripts/business/migrate_validate_outputs.py)，已接入本地启动脚本，备份在 `deploy/verification/.cache/validate-output-migration`。迁移前后会检查并发修改并回读确认；重复执行不再改变已迁移画布。

## 2. 已修正：质量检查不筛选业务范围

旧画布在 SettlementChecks 中配置 `OP_EM_MARK = "3"`，导致一条数据完整的普通门诊记录也被标为质量问题。问题根源是流程配置将“是否属于住院核验范围”放进了校验条件，而不是 Business Validate 不具备校验能力。

已修改画布和 [搭建样例](../../src/frontend/tests/core/features/business-core-flow.recipe.ts)：

1. SettlementChecks 移除 OP_EM_MARK 等值条件，只保留 `CNT >= 0`、`PRIC >= 0`，以及原有非空和身份检查。
2. OP_EM_MARK 原字段和非空检查保留，供后续业务筛选/检查关联使用。没有从数据库、Required 列表或输出中删除该字段。
3. NormalPaid 使用 AND 组合：

   ```text
   MED_PAY_FLAG = "1"      医保结算
   LIST_TYPE = "301"       医用耗材
   OP_EM_MARK = "3"        住院
   REFD_SETL_FLAG = 0      正常收费、非退费
   ```

4. TargetNames 继续筛选 HILIST_NAME 包含“人工髋关节”或“人工膝关节”。

用户本轮举例写了 `OP_EM_MARK = "1"`；现有来源字典定义 1 为普通门诊、3 为住院，画布原值也是 3。因此本次迁移住院条件，不将住院改成门诊。

当前 Required 是 12 列：ORGAN_CODE、DATA_SOURCE、SETL_FEE_LIST_ID、PSN_NO、PSN_NAME、CERTNO、OP_EM_MARK、OP_EM_NO、UPDATE_TIME、HILIST_NAME、CNT、PRIC。Required 当前检查 NULL，不等于完整格式审核。数值条件仍是非负（允许零），本次没有改为严格大于零。

## 3. 已修正：LIST_TYPE 模拟值和说明

| LIST_TYPE | 用户提供的含义 |
|---|---|
| 101 | 西药中成药 |
| 102 | 中药饮片 |
| 103 | 自制剂 |
| 104 | 民族药 |
| 201 | 医疗服务项目 |
| 301 | 医用耗材 |

本地 PostgreSQL `public.core_flow_settlement_v1` 的 `MOCK-DETAIL-HIP` 和 `MOCK-DETAIL-KNEE` 两条明细，LIST_TYPE 已从占位值 `MOCK-CONSUMABLE` 改为字符串 `301`。库内逐行核对其他列完全不变。

同步更新 [样例文件](./fixtures/core-flow/settlement-rows.json)、[建表字段注释](./fixtures/core-flow/settlement.sql)、库内 LIST_TYPE 字段注释及[数据契约](./CORE-FLOW-DATA-CONTRACT.md)。六项码表作为字段说明，不另造五类药品/服务的持久业务数据；两条髋膝样例都属于医用耗材。

LIST_TYPE 判断耗材大类，HILIST_NAME 判断髋膝范围，二者不同。MED_CHRGITM_TYPE 是另一字段，本次未把 LIST_TYPE 码表套用过去。附件提取文件 settlement-fields.json 保留原始数据字典证据，新增依据记录在契约和当前字段注释中。

## 4. 验证与边界

已启动完整本地项目。业务配置仅修改上述两个节点；核心画布的四个 Validate 组件输出均升级为两口，其原有连线都来自 Valid，无需添加分流节点。范围配置修改前备份在 `deploy/verification/.cache/settlement-scope-before-20261013.json`，输出迁移另有备份。既有发布包不就地修改。

使用数据库实际预览记录、保存后的节点配置及真实 Runtime.run_node 执行器，在临时 DatasetStore 中单独运行质量检查和业务筛选：

| 场景 | SettlementChecks | NormalPaid |
|---|---|---|
| 本地模拟库的两条髋膝记录 | Valid 2、Issues 0 | Matched 2、Unmatched 0、Unknown 0 |
| 另加 8 条质量合格但范围不符记录：101/102/103/104/201 各一条，门诊/非医保/退费各一条 | 加入的 8 条全部进入 Valid | 加入的 8 条全部进入 Unmatched |
| 另加负数量、患者编号为空各一条 | 两条进入 Issues，原因为 condition:CNT、required:PSN_NO | 不进入正常筛选输入 |

附加的 10 条边界记录只存在于临时测试数据集中，没有写入模拟源数据库。搭建样例中的两个节点配置也已与保存后的画布对照一致。

新增回归覆盖：重复金额只计一次、提示不阻断汇总、不增加待处理数量、冲突及负数量仍阻断、原始出现覆盖不丢失、旧画布迁移幂等且保住两类消费者、拒绝未知源码、新耗材模板的重复影像不导致结果冲突，以及旧发布版本迁移保留原包。另有任务页分类展示的 Jest 测试。

最终检查：完整 Business pytest **79 项通过、0 跳过**，已开启本地 MySQL/PostgreSQL 集成；前端 BusinessPage **5 组、17 项通过**。模拟库正常两条以及 12 条临时范围/质量样例在两口执行器上再次验证通过。

本地迁移扫描 21 张画布，更新其中 3 张：髋膝核心画布新增节点/连线为 0/0；跨库和耗材示例各增加 2 个分流 Filter。启动时发现早先“监管任务入口验收”仍启用旧运行版本，已按原配置重新发布兼容版本（v1→v2，业务图不变），没有改写其历史版本。两个通用示例同样按既有启用版本完成兼容升级，核心髋膝画布未发布。

格式与静态检查：修改的后端文件通过 Ruff；Tasks 与新增前端测试通过前端 Biome 配置检查；搭建样例 TypeScript 转译及格式检查通过。仓库直接运行 Biome 遇到嵌套根配置，因此在临时目录按同一前端配置检查；搭建样例已有的 `Record<string, any>` 未改，不宣称该样例全文件 lint 全绿。完整回归最终结果见验收证据。

真实 Chromium 已打开核心画布，确认 SettlementChecks 渲染 Valid、Issues，不再显示 Duplicates；四个 Validate 节点的保存定义均为两口，浏览器只读验收没有改变画布。完整启动脚本最终退出成功，Worker 已启动、任务受理为 open。证据：[review-report.json](./evidence/settlement-checks-20261013/review-report.json)、[实际数据库预览](./evidence/settlement-checks-20261013/preview.json)、[浏览器报告](./evidence/settlement-checks-20261013/browser-report.json)。

验收范围包括 Settlements 的当前模拟数据、SettlementChecks → NormalPaid 的行为、通用 Validate 执行与迁移兼容性。本次没有运行或重新发布整张髋膝流程，不据此宣称整张画布已完成业务验收。
