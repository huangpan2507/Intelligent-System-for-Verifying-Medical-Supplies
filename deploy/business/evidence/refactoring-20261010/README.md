# 2026-10-10 改造证据

- `backend-tests.txt`：最终 32 项通用／改造／真实 MySQL、PostgreSQL 及 HTTP 数据源测试。
- `republish-test.txt`：补充的不可变版本重新发布测试 1 项。
- `legacy-regression.txt`：旧固定核验回归 126 通过、1 跳过。
- `ruff.txt`：业务核心 Python 检查。
- `typescript-baseline.txt`：全仓 TypeScript 的既有错误，未宣称全仓类型检查通过。
- `api-schema-before.txt`、`api-schema-after.txt`：API 类型转换丢失原始批次的失败断言及修复后针对性结果，最终也纳入 32 项回归。
- `million-rows.json`：本次实际百万行双库测量，不是估算值。
- `live-acceptance.json`：已启动项目中的公共 API、Worker、分页结果、来源隔离和旧历史数量检查。
- `adversarial-task.json`：18 次原始出现的高值耗材反例任务摘要，使用模拟数据。
- `browser.txt`、`results-and-requests.png`、`canvas-obligation.png`：真实页面的 Playwright 通过记录及截图。仅外部模板商店标签使用空夹具，业务 API 不使用夹具替代。

测试中的地址、业务标识及影像引用均为本地构造样例；本目录不保存连接密码和访问令牌。临时 benchmark 数据目录只在运行机器上有效，JSON 中的该路径不是长期下载入口。
