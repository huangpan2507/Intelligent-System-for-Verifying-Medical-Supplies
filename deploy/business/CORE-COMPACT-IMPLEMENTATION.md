# 髋膝核心流程：10 节点实现与验收历史

日期：2026-10-14。依据：[已确认方案](CORE-FLOW-NODE-SIMPLIFICATION.md)及用户随后“请修改代码”的授权。范围为数据库＋API 的髋膝正常核心链路；Q24 确认的跨业务验收继续后置。

后续配置体验改动：Q25—Q33 已实施，包括字段用途、类别去向、紧凑规则、自动模型约束、移除模拟“其他”规则、全部关键词匹配、歧义转模型，以及 Data/Issues 两口和逐条去向统计。按用户后续决定，已经删除弃用 Classification 方案的兼容分支。该阶段启用发布版本为 **3**，为 10 节点；[新任务](http://localhost:3000/business/tasks/dda92490-dced-4144-aded-f73b2bd0ad2d)已完成。最新记录见 [Classification 实施与验收](CLASSIFICATION-CONFIGURATION-IMPLEMENTATION.md)。本文以下保留首次精简时版本 1 的实现与验收历史。

## 直接查看

2026-10-14 后续要求已实施：DR／CT、EXAM_PART、内置版本化标准字典与独立检查适用性步骤已经加入同一画布，当前启用第 4 版、11 个节点。详见 [最新实施记录](STUDY-RELEVANCE-IMPLEMENTATION.md)。本页其余内容保留此前 10 节点阶段的验收历史。

- [当前精简画布（已升级为 11 节点）](http://localhost:3000/flow/ce588a72-0614-4d84-badd-0e4355c427e6)
- [已完成的精简流程任务](http://localhost:3000/business/tasks/c07d6d7a-8419-42aa-8731-9fd76ceaeb47)
- [原 42 节点画布](http://localhost:3000/flow/e55b03b0-7c7f-420b-b720-33b1a4cf5559)

新方案代码为 `core.normal.compact.v1`，发布版本为 1。创建独立画布，未覆盖原图；既有任务和发布历史保留。执行器能力变化后，其他已启用方案从其原发布包重新发布兼容版本，不使用可能尚未完成的草稿替代。详见 [发布记录](evidence/core-compact-20261014/deployment.json)。

## 左栏、模板和主画布

Business 左栏新增 **Business Classification**、**Business Database Lookup** 两种类型。已有 Database、Validate、Transform、Filter、Join、Union、Aggregate、Model 等保留。API、Imaging、Compare 的增强均通过可选配置启用，既有配置仍按原方式运行。

业务方案模板增加“髋膝核心流程”。模板含字段、规则、关联和核验配置，连接留空，创建后绑定本环境的真实连接；已发布的验收画布已绑定本地模拟数据库和已配置服务。业务预设先保存在完整流程模板的节点配置中，没有新增独立的预设管理系统。

| 次序／画布实例 | 节点类型 | 本轮实现的业务处理 |
|---|---|---|
| 1 Task Start | Business Task Start | 提供任务医院、起止时间、规则及任务标识，保持只读任务展示 |
| 2 Settlements | Business Database | 按医院、期间、医保支付、301 医用耗材、非退费读取结算；无住院限制 |
| 3 SettlementChecks | Business Validate | 必填、数值和业务身份检查；完全重复只计一次，Valid／Issues 两个出口 |
| 4 Classification | Business Classification | 可读规则优先，无法确定时调用文本模型；核对引用与已配置冲突条件，保留类别、依据、置信度和去向 |
| 5 Studies | Business Database Lookup | 以医院＋系统＋申请单号查询检查，转换真实 chk_dt 类型，核对患者、就诊、期间、模态及部位 |
| 6 Series | Business Database Lookup | 以医院＋系统＋ris_study_id 查询序列，核对 link_id，返回 global_id 作为 series_id |
| 7 Images | Business API | 请求影像列表，拼接 domain＋file_path，按原耗材身份收集影像清单 |
| 8 Observation | Business Imaging | 调用独立模拟观察服务，在节点内部核对确认状态、数量、单位及依据 |
| 9 Compare | Business Compare | 内部计算两侧数量×单价，比较类别／数量／金额，并直接命名业务结果列 |
| 10 Results | Business Output | 保存展示结果、依据和每条源明细的覆盖核算 |

共 **9 种类型、10 个实例**，其中 Database Lookup 使用 2 次。原 42 节点中用于字段整理、条件判断、分流和回连的辅助步骤移入相应能力；中间数据集和请求记录仍可在任务详情查看。

## 字段与执行边界

- 数据库关联的左侧下拉来自上游结构；右侧来自所选连接、Schema、Table 的真实元数据。返回列显式设置别名，后续核对使用真实返回结构。两侧字段不会混用。
- 检查、序列按上游实际复合键去重后分批查询，每批最多 500 组键，不先扫描整张序列表。关联结果同时保留两侧追溯关系。
- `chk_dt` 取数据库原值，按配置的 `Asia/Shanghai` 转换为可比较时间。检查查询和结算查询均使用监管提交的起止时间，不恢复“前 7 天”口径。
- 分类类别、规则、证据列、冲突条件、模型连接和提示词均为配置，不在执行器内固定髋／膝字段。模型只接收已选名称字段；不通过 CNT 或 PRIC 猜类别。置信度用于展示，不设置自动放行阈值。
- 影像清单按原耗材身份分组，同组内相同拼接地址只保留一次，不跨耗材合并上下文。原始响应及影像标识仍保存。该机制不等于已经完成“相同影像标识却返回不同地址”等所有异常场景验收。
- CNT、PRIC 原样保留。观察数量来自独立观察返回；两侧都按套计，单价按元／套。金额为数量×同一单价，不声称核对独立的医院原账单金额。
- API 的 collection、Imaging 的 result_checks、Compare 的 calculations 等可选配置折叠展示。中文、英文新标签已提供；其他已有语言暂使用英文新增标签。
- 任务详情默认打开业务输出。页面验收发现原先直接选择 `results[0]`，而该位置可能是覆盖统计表，因此已改为优先选择结果集合中的 Data 输出；用户仍能切换到统计和中间数据集。

## 实际运行结果

真实 Worker 任务 `c07d6d7a-8419-42aa-8731-9fd76ceaeb47` 已完成全部 10 个节点。使用本地 PostgreSQL 结算表、MySQL 检查和序列表、模拟影像 API／观察服务，以及已配置的真实在线文本模型。

| 样例 | 分类方法 | 结算数量／单价 | 影像引用数 | 独立识别数量 | 类别／数量／金额 |
|---|---|---|---:|---:|---|
| MOCK-DETAIL-HIP | 规则 | 1 套／10,000 元每套 | 2 | 1 | 全部一致 |
| MOCK-DETAIL-KNEE | 在线模型 | 1 套／5,000 元每套 | 2 | 1 | 全部一致 |

膝关节样例为门诊记录，证明没有重新引入住院限制。选择模型的原因是名称未命中当前明确规则，不是“膝关节固定走模型”。本次文本模型调用 1 次，独立观察调用 2 次。

结算、质量有效记录、分类目标、检查关联、序列关联、影像清单、观察、比较和最终结果均为 2 行；4 张影像没有变成 4 次收费。类别、数量、金额共 6 项核验全部一致，覆盖缺口为 0。已按原明细编号逐条对照原 42 节点已验收结果，关键业务值一致。

证据：[验收汇总](evidence/core-compact-20261014/acceptance.json)、[最终结果](evidence/core-compact-20261014/result-rows.json)、[完整任务回执](evidence/core-compact-20261014/task.json)、[10 节点配置](evidence/core-compact-20261014/graph.json)。

## 回归与复验

- 业务后端全部专项回归：**111 项通过**，显式启用真实 PostgreSQL／MySQL 测试，无该类跳过。[日志](evidence/core-compact-20261014/backend-tests.txt)
- 前端 Business 配置和任务页：**6 组、19 项通过**，包含上游与远端数据库字段分别选择，以及默认显示业务结果、仍可切换覆盖统计的检查。[日志](evidence/core-compact-20261014/frontend-tests.txt)
- 本次 Python 改动通过 Ruff；前端改动通过 Biome 格式检查。
- Chromium 浏览器端到端验收：**1 项通过**。实际验证左栏新增节点、10 个画布实例、检查／序列的真实字段下拉、影像清单配置，以及任务页默认的两条最终核验结果。[日志](evidence/core-compact-20261014/browser-tests.txt)
- 全量 TypeScript `tsc --noEmit`：**通过**。本机默认堆限制下的前两次限时检查未完成；本次以 4GB 堆上限完成全量检查，耗时约 457 秒，无类型错误，未修改项目的编译设置。最后一次测试文案修订后增量确认也已通过（约 14 秒）。[全量日志](evidence/core-compact-20261014/typescript.txt)、[最终确认](evidence/core-compact-20261014/typescript-final-confirmation.txt)

浏览器截图：[序列关联配置](evidence/core-compact-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/compact-lookup.png)、[最终结果页面](evidence/core-compact-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/compact-results.png)。右侧配置面板覆盖节点时，可先折叠面板再选择节点。

在项目根目录复查已保存任务（不会再次调用付费模型）：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python -m scripts.business.verify_compact_core \
  --task c07d6d7a-8419-42aa-8731-9fd76ceaeb47
```

省略 `--task` 会提交新任务并按需实际调用在线模型。`apply_compact_core` 默认只预检；`--apply` 要求入口处于维护状态且已受理任务清空。

复验当前本机浏览器（使用已安装的 Chromium）：

```bash
BUSINESS_CHROMIUM_EXECUTABLE=/home/huangpan/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome \
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python -m scripts.business.verify_compact_browser
```

该脚本查看已有验收任务，不重新提交模型任务，不使用项目默认的 Playwright 服务／数据库清理步骤。服务仍可用项目已有脚本 `bash scripts/business/start_local.sh` 完整启动。

最终服务检查：任务入口开放、等待任务为 0，前端／平台 API／任务 API／两个模拟服务均返回 200，后台 Worker 会话存活；5 个已启用方案的执行器指纹均匹配当前代码。见 [健康检查记录](evidence/core-compact-20261014/health.json)。

本轮证明这批受控髋膝正常样例及配置的端到端结果一致。真实影像识别效果、完整异常分支和其他行业复用验收仍未纳入本轮；不能由两条模拟样例推断这些工作已经完成。
