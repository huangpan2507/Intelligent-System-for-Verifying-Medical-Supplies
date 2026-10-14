# Classification 配置与两口结果实现

日期：2026-10-14。依据：用户确认 Q25—Q33 后授权实施。对应 [设计记录](CLASSIFICATION-CONFIGURATION-REVIEW.md) 和 [ADR-0003](../../docs/adr/0003-classification-issues-include-exclusions.md)。本轮仅验收髋膝核心链路；跨业务验证仍按 Q24 后置。

用户后续更正：项目处于从 0 到 1 的建设阶段，已经舍弃的方案不需要兼容。当前 Classification 仅实现已确认的配置和两口契约；不维护旧三口、双套配置或旧提示词模式。历史任务数据的保留不构成旧实现继续可执行的承诺。

## 已落地的配置

- **分类字段**：五个字段只配置一次。PRODNAME、HOS_PROJ_NAME、MEDINS_LIST_NAME 为分类依据；HILIST_NAME、SPEC 为辅助上下文。两种用途都发送模型，明确类别仍须引用依据字段中实际存在的连续原文。
- **类别与去向**：人工髋关节、人工膝关节继续；其他排除。无法确定是单独的系统状态，不再手填。修改类别不会偷偷改掉已有规则引用，失效引用会提示并阻止发布。
- **紧凑规则**：公共字段自动取自分类依据；规则只维护匹配方式、文字／词组、输出类别。需要时展开选择依据字段子集。省略 fields 表示继承公共字段；保存了 fields 则始终表示明确覆盖。
- **包含全部关键词**：髋规则为“人工＋髋关节”，膝规则为“人工＋膝关节”。要求全部完整词组在同一字段出现，顺序不限，不允许跨字段拼凑。contains（连续包含）、eq（完全相等）也是当前可选择的匹配方式。
- **歧义提示**：本模板配置“未使用”“非人工”“取出器”。检查所有规则命中的原文；触发后交模型，记录触发字段、原文及提示。此状态与硬性事实冲突分开，模型可进一步判断歧义，但不能覆盖已确认冲突。
- **模型配置**：系统根据字段用途、类别自动生成约束，用户编辑业务说明。可展开查看实际发送的完整系统指令；单条记录的所选字段作为用户消息发送。预览不调用模型。路径、调用上限、已知冲突折叠为高级项。
- **模拟规则清理**：正常模板不再包含“等于非关节耗材（模拟对照项）→其他”；这条构造规则只用于本次新增的对照测试。规则未命中仍交模型，不能直接归为其他。

## 输出与统计

Classification 对外仅有 Data、Issues：

| 数据 | classification_disposition | 去向 | 待处理计数 |
|---|---|---|---|
| 目标类别 | continue | Data → Studies | 不增加 |
| 明确非目标 | excluded | Issues | 不增加 |
| 无法确定／依据不被接受 | uncompared | Issues | 增加 |

保留原始结算字段、分类方式、原因、证据字段、证据原文、自报置信度；新增 classification_ambiguity、classification_disposition、classification_disposition_reason。rules、model_input、model_data、model_issues、classification_results 中间数据仍可追溯。模型原始响应失败不再作为第二份最终 Issues 重复计数。

Results 使用 Issues 的逐行状态及原因核算去向，不能再给整个混合口赋一个固定状态。只接 Data 可以正常执行；Issues 无须接额外节点也会保存。本核心流程已配置其结果核算引用，任意新流程仍需配置自己的结果约定。

## 当前实现与运行方式

配置仅接受 classification_fields、category_routes、business_guidance 等当前字段。unknown_category 不再可配置，“无法确定”为固定系统状态。旧 input_fields／evidence_fields／categories／target_categories／prompt／legacy_prompt 不作为 Classification 的输入配置接受；运行时需要的字段名单从当前字段表推导。

当前髋膝核心画布为 **10 节点、9 条连线**，只有 Data、Issues 两口，Results 按 Issues 每行的状态核算去向。已经删除旧组件识别、旧三口转接、自动追加 Filter、旧模型指令保留及旧配置升级脚本。不合当前契约的旧配置需直接按当前设计修改，系统不会自动恢复弃用行为。

启动脚本在执行器代码更新后重新校验并发布活动方案。核心流程采用当前画布；其他方案采用其已选配置，避免替换为未确认的草稿。所有配置都必须满足当前能力契约，这个步骤不转换弃用的 Classification 格式。

```bash
# 在项目根目录启动／重启全部服务，校验当前配置并启动 Worker
bash scripts/business/start_local.sh --restart
```

## 移除弃用方案后的验收

当前画布：[髋膝关节正常核心流程（数据库＋API，精简10节点）](http://localhost:3000/flow/ce588a72-0614-4d84-badd-0e4355c427e6)。方案 `core.normal.compact.v1`，当前发布版本 **3**，发布编号 `2f030872-24a4-4d02-8e1c-da9d01245d0b`。

已核对画布为 10 个节点、9 条连线，Classification 只有 data、issues；没有弃用配置字段、版本转换标志或额外 Filter 适配节点。预检错误为 0。[配置核对记录](evidence/classification-current-only-20261014/deployment.json)。

| 检查范围 | 结果 | 证据 |
|---|---|---|
| 全部业务后端专项回归，启用真实 PostgreSQL／MySQL 测试 | 135 项通过，无跳过 | [日志](evidence/classification-current-only-20261014/backend-tests.log) |
| 前端 Business 配置与任务页回归 | 7 组、23 项通过 | [日志](evidence/classification-current-only-20261014/frontend-tests.log) |
| Python Ruff | 通过 | [日志](evidence/classification-current-only-20261014/ruff.log) |
| 前端 Biome | 通过 | [日志](evidence/classification-current-only-20261014/biome.log) |
| 全量 TypeScript | 通过，退出码 0 | [退出状态](evidence/classification-current-only-20261014/typescript-status.txt)、[日志](evidence/classification-current-only-20261014/typescript.log) |
| 真实 Worker 核心任务 | 通过，10 个节点全部完成 | [验收汇总](evidence/classification-current-only-20261014/acceptance.json) |
| Chromium 浏览器核心验收 | 1 项通过 | [日志](evidence/classification-current-only-20261014/browser-tests.log) |

当前回归直接验证：字段用途和类别驱动模型约束；无法确定为固定系统状态；弃用配置键和非当前组件代码被拒绝；画布保存／读取不追加节点；同字段全关键词匹配及歧义转模型有效；只连接 Data 时非空混合 Issues 仍保存，排除与待处理分别统计；逐条结果核算无遗漏。

检查汇总：[validation.json](evidence/classification-current-only-20261014/validation.json)。浏览器截图：[分类字段](evidence/classification-current-only-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/classification-fields.png)、[紧凑规则](evidence/classification-current-only-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/classification-rules.png)、[任务页面](evidence/classification-current-only-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/compact-results.png)。

核心验收脚本已移除对旧 42 节点结果文件的依赖，直接核对当前已确认的髋、膝两个模拟样例：各 1 套，单价分别为 10,000 元／套和 5,000 元／套。文本分类使用真实在线模型；影像识别继续使用约定的模拟服务。跨业务验收仍按 Q24 后置。

[本次任务 dda92490-dced-4144-aded-f73b2bd0ad2d](http://localhost:3000/business/tasks/dda92490-dced-4144-aded-f73b2bd0ad2d) 已完成。两条记录的类别、数量、金额共 6 项比较全部一致，覆盖缺口及待处理数均为 0，分类统计为继续 2、排除 0、无法确定 0。真实文本模型请求 1 次，独立模拟影像识别请求 2 次。只连接 Data 时非空混合 Issues 的行为，由专项回归单独覆盖。

使用既有任务复验，不会再次调用模型：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python python \
  -m scripts.business.verify_compact_core \
  --task dda92490-dced-4144-aded-f73b2bd0ad2d \
  --evidence-dir deploy/business/evidence/classification-current-only-20261014
```

完整项目已重启，前端、平台 API、业务 API、Worker、两个模拟服务及三个数据库已启动。[启动日志](evidence/classification-current-only-20261014/startup.log)。

首次实现时的运行证据仍保存在 `evidence/classification-config-20261014`；其中兼容旧配置、旧端口的验收目标已撤销，不是当前实现要求。

国际化：提供中英文，其他五种语言的新增文案采用英文占位。有限关键词／提示词和模拟样例验收不代表真实医院数据上的分类准确率；本轮未验收真实影像识别服务。
