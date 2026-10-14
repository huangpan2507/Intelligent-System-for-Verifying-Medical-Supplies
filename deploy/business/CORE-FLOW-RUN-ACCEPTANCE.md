# 正常核心路径实施与运行验收

> 2026-10-13：用户已变更检查、序列数据源，参见[数据库来源变更](./CORE-FLOW-DATABASE-SOURCE-CHANGE.md)。以下 32 节点预检及搭建进度属于旧方案；新方案尚未执行，不沿用旧预检作为验收证据。

> 新数据源准备已完成：结算 51 列、检查 94 列、序列 164 列，均可由平台发现字段；两段数据库关联与影像 API 验证得到 2 组关联及 4 条影像引用，见[准备报告](./fixtures/core-flow/database-sources/preparation-report.json)。此项不代表整张画布已运行或最终比较已验收。

日期：2026-10-12。当前状态：实施中，尚未通过整张画布运行验收。

## 本轮业务口径

- 监管输入医院名字、开始时间、结束时间。Database 按 `ORGAN_NAME`、`UPDATE_TIME` 筛选；检查 API 使用同一组 `start/end`，不再向前推 7 天。
- 实际检查时间来自 `data[].chk_dt`。只为类型比较补充明确的北京时间偏移并转换类型，保留原始字段。
- 影像地址直接拼接 `domain + file_path`。本轮使用模拟地址和独立模拟观察结果，不表示真实影像下载或医学模型准确率验收。
- 髋、膝各一组；数量均为套，价格为元/套。分别以结算数量和独立观察数量乘以同一单价比较金额。
- 只验收正常核心路径，不展开异常业务分支。

## 已实施修复

| 问题 | 根因 | 修复 |
|---|---|---|
| 时间参数不能稳定用于 PostgreSQL 时间列 | 无时区字符串被作为字符串绑定；反射类型字符串遗漏时区信息 | 依照真实列类型转换参数，明确 `Asia/Shanghai`；反射和预览保持 `TIMESTAMP WITH TIME ZONE` |
| 无法在 Transform 中拼接影像地址 | 安全表达式函数白名单未提供拼接 | 增加 `concat`，保留路径中的签名、查询参数等原值 |
| 所有节点都显示三个输入口 | 基类统一暴露 Data、Left、Right | 按节点能力声明显示输入口；Join 保留左右口，Union 支持多路，Database 显示可选参数依赖，Parameters 不显示数据输入 |
| 条件值来源可能相互冲突 | 常量、任务参数、上游字段同时出现，没有排他编辑方式 | 表单提供来源选择并清除旧来源；参数下拉取自已声明参数；编译时拒绝多个来源 |
| 搜索 Business 节点时整个结果分组消失 | 当前侧栏可见性判断使用的分类表遗漏 Business | 在实际使用的侧栏分类表登记 Business，并补充各语言标签 |

## 验收方式与当前证据

通过 Playwright 使用真实界面创建空白方案，添加、重命名、排列和连线节点，再逐项填写表单。未通过 API 或前端状态仓库注入完整业务图来替代搭建。

- 画布：[髋膝关节正常核心流程](http://localhost:3000/flow/e55b03b0-7c7f-420b-b720-33b1a4cf5559)。方案代码 `core.normal.1791804428546`。
- 配置步骤：`src/frontend/tests/core/features/business-core-flow.recipe.ts`，共 32 个节点。
- 当前界面进度：`evidence/core-flow-20261012/canvas-checkpoint.json`。
- 32 节点只读配置预检：`inspect_graph(..., strict=False)` 返回 `errors={}`；此检查不执行或发布工作流。
- 当前代码核心回归：3 项通过，含真实 PostgreSQL 时间边界查询；日志 `evidence/core-flow-20261012/core-path-tests.txt`。

最终整图验收标准：2 条结算、2 条检查、2 条序列、4 条影像引用、2 份清单、2 条独立观察、2 条结果；类别/数量/金额共 6 项一致，数量差和金额差均为 0，业务核验无未交代记录。

## 完整项目启动

```bash
bash scripts/business/start_local.sh
```

前端 3000、平台 API 7860、任务 API 18081、worker、模拟接口 8090/8091，以及元数据库 PostgreSQL 55433、业务 PostgreSQL 55434、业务 MySQL 13306 均已启动。启动过程保留原有数据库和画布；服务由 tmux、数据库由 Docker 保持。
