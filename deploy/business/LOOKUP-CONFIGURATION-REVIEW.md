# Database Lookup 配置体验梳理

日期：2026-10-14。范围：Studies 的 Schema 解释、来源身份配置和表单布局。
状态：用户已同意 Q39—Q41，随后授权实施；代码和运行画布已修改。实施与验收状态见 [实施记录](LOOKUP-CONFIGURATION-IMPLEMENTATION.md)。本文保留设计时核实的事实和决策依据。

## 已核实事实

当前画布已是 11 节点，Studies 为第五节点；后接独立的 StudyRelevance。

Settlements 连接 PostgreSQL，本地模拟库 business_demo 下的 public.core_flow_settlement_v1；Studies 连接另一套 MySQL，本地模拟库 business_demo 下的 INSPECTION_INFO_RECORD。两者库名相同不表示同一个数据库。
PostgreSQL 的 schema 是库内的命名空间；MySQL 的 schema 与 database 在此处同义。public 是 PostgreSQL 常用的初始 schema，不表示无需权限或互联网公开。两个值均对应真实本地数据库结构，不是节点虚构的选项，也没有髋膝业务上的特殊含义。
来源元数据由 connections.metadata 的数据库反射获取，尚未运行任务也能查询。

Source identity 当前配置 name=study、namespace=core-study-v2，keys 为 organ_code、system_id、ris_study_id。relational.identity_queries 使用 namespace:name:身份键JSON 拼接内部身份值，没有对这部分执行哈希。两项不是源表列，也不是纯显示标签。
同一批记录使用相同前缀，因此修改前缀通常不改变本批去重分组，但会改变保存的身份值。模板已预填；通用节点目前没有自动生成这两个值的默认逻辑。
Lookup 通过内部 source-quality 检查源记录，再关联上游。源身份并不自动成为输出字段；行级溯源另有数据集与行之间的关联记录。

关联条件（ORGAN_CODE/SYSTEM_ID/RPT_NO 对应源表字段）和检查身份（organ_code/system_id/ris_study_id）不同：一张申请单下可有多次检查。不能为了减少配置，把两组键自动合并。
Source required 和 Checks.required 分别作用于来源记录、关联结果；当前为空检查主要针对 NULL，不能将界面文案扩大解释为空白文本或全部业务有效性检查。

## 布局根因

catalog.py 将十项顶层配置并列提供给 SchemaForm；CanvasConfiguration 只特别调整 Connection、Schema、Table 的顺序。SchemaForm 对对象和数组递归生成表单，每一数组元素都有边框、内边距、删除按钮。右侧编辑面板固定 w-96。
后果：技术配置和业务配置平级；同一字段选择占据大卡片；关联前的条件与关联后的检查难以区分；14 条返回映射和6条结果条件造成长页面。仅缩小字体不能解决结构问题。

## 已确认布局（Q40）

1. 数据来源：连接 → 按数据库类型显示 Schema／数据库 → 表。
2. 如何关联：上游字段 ↔ 来源表字段的紧凑对应行，来源标识清晰。
3. 取数范围：医院、任务起止时间等数据库查询条件。
4. 带回哪些字段：来源字段 → 输出名称；类型转换、时区按单行需要展开。保留现有别名及下游引用。
5. 来源记录质量：认定同一检查的字段、多选必填字段；显示身份范围摘要。内部标识依 Q39 处理。
6. 关联后核对：患者、证件、就诊、DR/CT、检查时间等条件；使用紧凑条件行。

面板顶部展示上游来源，底部固定说明 Data/Issues 含义；每组折叠时显示配置数量及业务摘要，错误计数可见并可展开定位。宽编辑区采用紧凑表格，窄面板使用两行对应布局，保留可辨认的完整字段名，不强制横向滚动或缩小字号。
没有任务时展示配置摘要，不能伪装为已关联检查。保持当前执行条件、字段映射、质量检查和 Data/Issues 语义；本轮不把部位语义判断移回 Lookup。

## 设计树与已确认决策

- Q39（已同意：系统管理内部标识）：普通使用者只配置真实身份字段；Name/Namespace 改由系统稳定管理，在只读技术详情中可查看。保留有效既有标识，新节点生成后持久保存，重命名节点不改变身份值。模板预设身份字段可调整，系统不猜哪组业务键唯一。
- Q40（已同意：六组布局与紧凑编辑）：采用上述六组业务表单、紧凑映射/条件行、可展开宽编辑区；折叠显示摘要和错误，不删实际业务能力，不改执行口径。
- Q41（已同意：按数据库类型展示与预选）：PostgreSQL 显示“Schema（库内命名空间）”，MySQL 显示“数据库”；优先显示已保存的真实选择。新配置在数据库反射确认连接默认范围有效时预选并展示，仍允许切换其他有权限的范围；无法确认有效默认范围时保留明确选择，不硬编码 public/business_demo。更换来源后提示受影响字段，不静默换表或替换映射。

用户已在同一轮明确同意全部三项，本轮设计没有未决问题。实施范围为上述配置体验调整，不新增检查业务规则，不改变现有身份字段和输出映射的含义；后续已单独授权修改代码和运行画布。

## 实施后验收要求（方案）

- PostgreSQL/MySQL 的范围标签和真实元数据一致；更换连接/Schema 后失效字段可见，不悄悄采用同名字段。
- 新建、保存、刷新、重命名节点时，系统管理的来源身份标识稳定；现有模板无需手填 Name/Namespace。
- 保留三组关联键、三组身份键、三条取数条件、14条返回映射、6条结果条件；保存前后语义相同。
- 紧凑多选及条件编辑具有可访问名称；长字段可完整辨认；折叠区中的错误不会被隐藏。
- 当前受控任务预期仍是2条耗材关联5次检查，Studies.Data 5行、Issues 0行，最终2条耗材金额不因多检查倍增。

代码依据：src/backend/base/langflow/business/{catalog,connections,relational,lookup}.py；src/frontend/src/pages/BusinessPage/{CanvasConfiguration,SchemaForm}.tsx。既有实施与运行证据见 STUDY-RELEVANCE-IMPLEMENTATION.md。
