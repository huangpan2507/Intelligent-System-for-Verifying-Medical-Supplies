# 通用业务平台验收记录

验收日期：2026-10-09。环境：当前 WSL 工作区、Docker Desktop、现有 Langflow 和业务 PostgreSQL。以下是本次实际执行结果，不是预估容量或生产性能承诺。

这是改造前初版的验收记录，不能代表 D01—D07 改造后的行为。最新工程验证见[2026-10-10 改造验收记录](./REFACTORING-ACCEPTANCE.md)。

## 功能与回归

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 通用数据与流程测试 | 14 项通过 | `/tmp/business-tests.log` |
| 原核验 API、发布、历史查询回归 | 44 项通过 | `/tmp/business-legacy-regression.log` |
| 真实 MySQL/PostgreSQL 集成 | 1 项通过 | `/tmp/business-database-tests.log` |
| 原生画布及全栈浏览器 | 登录、方案、结果表、字段下拉、自动保存、连线保留、重新发布通过 | `/tmp/business-smoke.log` |
| 当前实际项目浏览器 | 结果表、配置面板处于视口内、保存后字段仍有效及全部连线保留通过 | `/tmp/business-local-browser.log` |
| 一键完整重启 | `bash scripts/business/start_local.sh --restart` 返回 0 | `/tmp/business-restart-final.log` |
| 重启后公共 API → Worker → 结果 | 两个方案均完成；分页数据、来源隔离、历史数量核对通过 | `/tmp/business-local-acceptance.log` |
| 新增通用后端静态检查 | Ruff 通过 | `/tmp/business-final-ruff.log` |
| 新增页面与 API hooks 静态检查 | Biome 通过 | `/tmp/business-final-biome.log` |

通用测试覆盖：跨批次汇总、全关联、重复键及受影响对侧保留、空值与未知分流、金额精度、连续校验与比较、合并、默认结果、固定版本子流程、逐条 API 与模型、模拟耗材链路、来源隔离与幂等、版本固定、原生连线序列化、拒绝未注册代码改动、历史排空及迁移后只读。

真实数据库测试使用不同表名和字段名、5001 条付款跨越 5000 行读取批次，并正确检出 `0.00000001` 差额。未参与比较的原始字段仍保留；源数据库只读事务拒绝 DELETE。只创建并清理专用随机测试表。

前端全仓 TypeScript 检查仍存在既有错误，例如 `NodeOutputfield` 的 `idx` 参数类型及旧测试的类型转换；本次新增 `BusinessPage` 与业务 API hooks 没有出现在错误列表中。不能宣称全仓 TypeScript 构建通过。完整日志：`/tmp/langflow-business-tsc.log`。

## 真实双库百万行

| 指标 | 结果 |
|---|---:|
| MySQL 输入 | 500,000 行 |
| PostgreSQL 输入 | 500,000 行 |
| 对比输出 | 500,000 行 |
| 相同 | 499,950 行 |
| 预置差异 / 检出差异 | 50 / 50 行 |
| 任务执行及测试表清理 | 15.591 秒 |
| 测试进程峰值 RSS | 565.5 MB |
| 持久数据目录占用 | 65.3 MB |

计时不含准备测试数据，峰值内存包括整个测试进程；临时溢出磁盘峰值未单独采样。结果目录占用不是磁盘峰值。数据规模、机器、数据库缓存、字段宽度、关联基数与并发变化都会影响结果。

原始报告：`deploy/verification/.cache/business-database-benchmark.json`。命令：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/benchmark.py --databases --output deploy/verification/.cache/business-database-benchmark.json
```

## 实际项目中的结果入口

重启后两条任务均使用方案 v2，通过公共 API 受理并由后台 Worker 执行：

- 跨库对账：[查看任务](http://localhost:3000/business/tasks/36c8e1dd-1640-48db-8844-23eb7838eccf)。默认结果 4 行，分别是相同、不同、仅订单侧、仅付款侧。
- 高值耗材模拟：[查看任务](http://localhost:3000/business/tasks/db976fb8-d5d5-46d0-bf2c-34ba579fe2d9)。默认核验结果 2 行；另保留分类未知 1 行、医保事实未知 1 行，可从结果页数据集下拉查看。

当前项目的浏览器截图：`/tmp/business-local-browser/task.png`、`/tmp/business-local-browser/canvas.png`。独立全栈环境的发布及重新发布证据位于 `/tmp/business-smoke-80hqrmfh/`。

结果页可以选择原始数据、各节点数据和问题分支，查看字段结构、分页记录、来源与依据。问题数按节点计数，可能包含同一业务对象在多个节点的记录，不应当作去重后的覆盖人数。

## 历史数据保留

迁移前后核对一致：

| 历史数据 | 数量 |
|---|---:|
| 任务 | 12 |
| 执行 | 12 |
| 规则发布版本 | 11 |
| 证据记录 | 88 |
| 已完成执行 | 8 |
| 原先需要确认的执行 | 4 |

4 条需要确认的旧执行均未实际开始，保留原状态，没有为了完成迁移改成成功或删除。已经开始且需要确认的执行会阻止迁移完成，允许管理员在排空期间确认；完成迁移后该确认接口返回 410。旧任务提交及重跑接口停止受理，旧规则与任务查询保留。

## 外部依赖与边界

真实运行了 MySQL/PostgreSQL 服务和持久任务机制，两个示例使用的业务记录均为构造数据。高值耗材中的目录、影像及识别响应是明确标记的模拟；真实医院数据源和专业模型仍需配置接入。

首期单部署执行、CSV UTF-8、文件上传 100 MB；日期时区或单位转换应在源 SQL 或流程的显式转换配置中完成。并发容量、生产数据权限及真实模型的业务准确率不包含在本次示例验收中。
