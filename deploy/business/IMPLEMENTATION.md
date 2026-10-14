# 通用业务平台实施记录

本次范围：MySQL/PostgreSQL、可视化优先、SQL 可选、百万行分批处理、原始字段封存、历史核验只读、高值耗材重建为可选模板。验收日期：2026-10-09。

本文记录初版。2026-10-10 基于 D01—D07 的后续改造及其实际限制见[改造验收记录](./REFACTORING-ACCEPTANCE.md)。

## 已实现

- [x] 数据集引用、字段结构、全量原始快照和 Parquet/DuckDB 关系运算。
- [x] 数据库/API/模型连接管理、凭据加密、表与字段元数据、有限行数预览。
- [x] 通用方案发布、启用、版本固定、受理、幂等、持久 Job 和来源隔离 API。
- [x] 14 类原生 Langflow 画布组件、统一可视化配置、上游字段下拉及配置校验。
- [x] API、CSV/JSON/Parquet、结构化模型调用、固定版本子流程及可选专业组件接口。
- [x] 连接、方案、任务、动态结果、问题分支、原始数据和历史记录页面。
- [x] MySQL/PostgreSQL 对账模板和高值耗材模拟模板，共用平台核心。
- [x] 旧入口关闭、已受理执行排空检查、保留原历史状态和只读查询。
- [x] 一键启动脚本、真实双库验证、百万行性能记录、浏览器完整链路及实际 Worker 验收。

## 实现位置

| 职责 | 位置 |
|---|---|
| 通用执行、编译、连接、数据集、API、模板 | `src/backend/base/langflow/business/` |
| Langflow 管理接口 | `src/backend/base/langflow/api/v1/business.py` |
| 原生画布组件 | `deploy/verification/components/business/` |
| 页面、表单、字段绑定 | `src/frontend/src/pages/BusinessPage/` |
| 前端 API hooks | `src/frontend/src/controllers/API/queries/business/` |
| 单元与数据库验证 | `deploy/business/tests/` |
| 启动、示例准备、性能及全栈验证 | `scripts/business/` |

高值耗材名称、医院参数、髋膝类别出现在模板配置和专业适配组件中；核心编译器、受理器和执行器不按这些业务名称选择路径。发布页不再维护另一份耗材目录映射。

## 交付边界

- 示例 MySQL/PostgreSQL 是实际数据库服务，里面的业务记录是人工构造的联调数据。
- 耗材、目录及影像示例明确标记模拟；未声称已经接入真实医院系统或医疗识别模型。
- 当前按单部署执行；不包含人工审批等待、源业务库写入或分布式大规模计算。
- 连线传数据集引用；文件上传首期限制 100 MB、CSV 使用 UTF-8，更大数据使用数据库批次读取。
- 中文、英文文案已提供，另外五种语言使用英文回退。
- 不覆盖原有未提交的设计图与报告，不删除旧数据库、任务、版本或证据。

使用方法、接口与验证命令见 [README.md](README.md)；结果和客观限制见 [ACCEPTANCE.md](ACCEPTANCE.md)。
