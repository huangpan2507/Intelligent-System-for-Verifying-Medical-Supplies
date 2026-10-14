# Business Database 配置界面调整

## 本轮已确认范围

用户要求两项小幅调整：数据库来源按 Connection → Schema → Table 排列；每条 Conditions 卡片最下方增加一句说明。暂不扩展字段悬浮说明或完整字段说明面板。

这些是可直接修改的界面呈现约定，不新增 ADR，也不改变查询规则、已有连接、画布配置或任务参数。

## 来源选择顺序

数据库节点的前三项固定为 Connection、Schema、Table；其余配置保持现有相对顺序。SQL 模式仍隐藏 Schema、Table 和 Conditions。

## 条件含义说明

每条说明位于该条件卡片的 Remove 按钮之后，由当前字段、比较方式和值来源即时生成，不保存成独立配置。

监管流程包含 Task Start 时，使用以下已有业务约定：

| 条件 | 简短说明 |
|---|---|
| ORGAN_NAME eq 参数 hospital_name | 使用监管端本次提交的医院名称，与数据库字段 ORGAN_NAME 比较，保留名称相同的记录。 |
| UPDATE_TIME ge 参数 start | 按数据库字段 UPDATE_TIME 筛选结算记录：结算时间不早于监管端提交的开始时间。 |
| UPDATE_TIME le 参数 end | 按数据库字段 UPDATE_TIME 筛选结算记录：结算时间不晚于监管端提交的结束时间。 |

其他字段或比较方式按当前条件展示通用说明，不能沿用医院相等或结算期间的旧说明；普通流程不宣称参数来自监管端。常量条件显示实际配置的常量，未完成字段、操作或参数选择时不显示完整比较说明。其他节点的条件卡片不增加这类说明。

说明只解释已配置条件，不证明字段已通过验证、任务已运行或结果已生成。结算期间沿用监管提交的起止时间，不新增检查时间窗计算。

中文及其他界面语言均通过现有翻译资源展示。任务参数的含义见 [任务入口约定](CORE-FLOW-REQUEST-REVIEW.md)，结算查询条件的术语见 [词汇表](../../GLOSSARY.md)。

## 验证

- 既有前端回归 11 项通过，覆盖画布配置、条件来源切换及任务输入面板。
- 修改的 10 个前端文件通过 Biome 检查；5 条新增说明在全部 7 个语言文件中均存在，插值变量一致。
- 全量前端 TypeScript 检查通过：`tsc --noEmit --pretty false --project tsconfig.json`，退出码 0。
- 真实 Chromium 页面验证通过：Connection → Schema → Table 顺序；三条核心说明；Remove 后的位置；字段、比较方式、参数、常量切换后说明同步更新；清空参数时清除旧说明；SQL 模式继续隐藏选表和条件。
- 浏览器验收使用核心画布的浏览器副本，读取真实数据库元数据，阻止验收期间保存画布；结束时确认服务端核心画布数据未变化。
- [浏览器验收记录](evidence/database-node-ui-20261013/browser-report.json)与[中文界面截图](evidence/database-node-ui-20261013/database-conditions-zh.png)。
