# Database Lookup 配置体验实施记录

日期：2026-10-14。依据：已确认的 Q39—Q41，以及修改代码和运行画布的请求。

状态：代码、运行画布及新任务验收已完成，完整项目服务已恢复运行。

## 改动

- Lookup 使用独立配置界面：数据来源、如何关联、取数范围、带回哪些字段、来源记录质量、关联后核对。
- 默认展开前两组，其余组显示配置数量、字段或条件摘要；折叠时仍可见缺失值、失效引用等配置问题计数。完整编译错误仍显示在面板顶部。
- 关联与返回映射使用紧凑行；返回类型和时区逐行展开。身份字段、来源必填字段、结果必填字段使用可搜索的复选列表；已选字段在搜索时仍可见，失效字段保留并明确提示。
- Lookup 可切换宽编辑区；使用正常字号，字段选择器保留完整选项和当前值提示。
- 选择身份字段后，系统补齐并保存 Name、Namespace，普通使用者无需填写。详情只读；已有模板的 study/core-study-v2 等有效标识保留，新配置使用稳定的节点内部 ID 生成命名空间。显示名称变化不重新生成身份值。
- 数据库元数据响应增加实际默认 Schema。PostgreSQL 展示“Schema（库内命名空间）”，MySQL 展示“数据库”；新配置只预选元数据确认存在的默认范围，保留现有明确选择。不硬编码 public 或 business_demo。
- Lookup 保存已确认的来源范围 binding_source。更换连接、Schema 或表后，原映射不被替换；提示核对包括同名字段在内的对应关系，核对状态随画布保存。未确认的新来源不能发布。此记录不改变查询条件，也不存放凭证。

文案新增到全部七个语言文件；中文、英文已提供，其他五种语言的新文案暂为英文。

## 运行画布

迁移脚本：scripts/business/apply_lookup_configuration.py。

原画布备份：deploy/verification/.cache/lookup-configuration-20261014/canvas.json。

在既有 Studies、Series 中保存已确认的来源绑定，保留节点、连线、位置和原业务配置。脚本逐项比较配置，确认原有条件、身份字段、返回映射没有变化，并执行编译预检和保存后回读。

本次不新增数据库字段或修改模拟数据。部位解释及模型判断仍由 StudyRelevance 承担，主画布仍为 11 个节点。

## 验收

最终结果和日志见 evidence/lookup-configuration-20261014/。代码测试、发布状态、真实 Worker 新任务和浏览器检查分别记录，避免将历史任务通过视为本次发布已经验收。

- 后端业务回归：149 项通过，启用真实 MySQL／PostgreSQL。
- 前端配置回归：8 组、31 项通过；覆盖身份字段编辑及标识稳定、保存后重开、更换来源后保留核对状态、上下游字段隔离、默认 Schema 预选与失效字段提示。
- 全项目 TypeScript 检查通过。首次检查发现分组标题使用过宽的动态翻译键类型，已限定为六个实际分组并复查通过；没有放宽翻译键约束。改动文件 Ruff／Biome 检查通过。
- 浏览器端到端验收：1 项通过，实际打开当前 11 节点画布，核对 Studies、Series 六组布局、数据库标签、真实字段选项、只读身份、宽编辑区及本次任务结果。
- 核心方案已启用第 5 版：`5defdbf5-e615-4a9d-99bc-85664a713964`。已核对保存画布、发布图及当前执行器指纹一致。
- 新任务 `a5d22e99-5ca8-45fb-880a-52f107d90b47` 已完成全部 11 个节点：2 条结算、5 次检查、5 条序列、12 个影像地址，最终回到 2 条耗材。类别、数量、金额全部一致，源明细覆盖缺口为 0。
- 在线文本模型实际调用 2 次；影像识别仍使用已约定的模拟服务，本次没有声称完成真实医学影像识别验收。

[运行画布](http://localhost:3000/flow/ce588a72-0614-4d84-badd-0e4355c427e6) · [本次验收任务](http://localhost:3000/business/tasks/a5d22e99-5ca8-45fb-880a-52f107d90b47) · [验收数据](evidence/lookup-configuration-20261014/acceptance.json)。

证据：[检查汇总](evidence/lookup-configuration-20261014/verification-summary.json)、[前端测试](evidence/lookup-configuration-20261014/frontend-tests.txt)、[后端测试](evidence/lookup-configuration-20261014/backend-tests.txt)、[浏览器日志](evidence/lookup-configuration-20261014/browser-tests.txt)、[宽编辑区截图](evidence/lookup-configuration-20261014/browser/core-features-business-com-badaa-rectly-scoped-lookup-fields/studies-grouped-wide.png)、[真实数据库元数据](evidence/lookup-configuration-20261014/database-verification.json)、[服务健康检查](evidence/lookup-configuration-20261014/service-health.json)。

## 复查命令

完整启动：`bash scripts/business/start_local.sh`。

只读复查本次任务，不再次调用模型：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python -m scripts.business.verify_compact_core \
  --task a5d22e99-5ca8-45fb-880a-52f107d90b47 \
  --evidence-dir deploy/business/evidence/lookup-configuration-20261014
```

浏览器复验脚本为 `scripts.business.verify_compact_browser`，使用同一 `--evidence-dir`。本机已安装 Chromium 1228，而项目默认查找 1223；本次通过环境变量 `BUSINESS_CHROMIUM_EXECUTABLE=/home/huangpan/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell` 指定已安装的浏览器执行验收。
