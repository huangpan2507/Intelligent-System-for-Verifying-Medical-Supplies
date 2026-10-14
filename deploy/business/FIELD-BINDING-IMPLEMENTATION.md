# Business 字段发现与绑定：实现与验证记录

日期：2026-10-12。依据：[已确认的 Q1—Q6](./FIELD-BINDING-DESIGN.md)。

代码已实现，可以在工作流运行前建立来源结构、选择上游字段并检查失效引用。本地自动化回归已通过；本次没有完成实际运行服务部署，也没有通过真实 MySQL/PostgreSQL 集成验证。

## 操作方式

### 数据库表

1. 拖入 Business Database，选择 Connection。
2. 选择 Schema 和 Table。未指定 Schema 时使用连接的默认 Schema。
3. 配置面板自动请求所选 Schema 的表和列；空表也可发现列，不需要运行工作流。
4. Conditions 的 Field 从真实列中选择；连线后的下游节点从该输出端口的结构中选择字段。
5. 需要样本记录时，再显式点击预览。表模式不再要求重复手工填写 Fields。

表列表和列列表请求都包含 Schema，避免不同 Schema 下同名表混用字段。后端编译同时检查条件字段；修改来源后，原来的无效引用保留并报错，不按名称相似度替换。

### SQL 查询

1. 在 Database 的 Sql 中填写只读查询，并声明 Parameters。
2. 在预览参数中填写独立测试值，点击预览，最多取得 25 行。
3. 结果字段采用查询实际返回的列名，包含 SQL 别名；确认类型后点击采用字段。
4. 空结果仍可取得结果列名，但缺少样本值的类型会显示待确认提示。
5. 修改 SQL、Connection 或查询参数声明后，必须重新预览并采用结构。

SQL 模式隐藏不参与该查询的 Table、Schema、Conditions 配置。预览不会创建业务任务；后端保存与来源、连接版本、用户关联的发现凭据，不能仅修改 JSON 就把未发现的字段冒充查询结果。

### API 契约或实际样本

先配置 Connection、Path、Method、Body 和 Items path，再展开专门的 API 字段区域。

- **服务方契约**：填写文档出处与版本，在专门入口录入字段名称、类型、属性是否必有、值是否允许 null，然后点击采用。也可以粘贴或上传 JSON Schema / OpenAPI JSON，并点击导入。普通下游字段引用仍使用下拉选择。
- **实际样本**：展开测试区域，填入测试参数、上游测试记录，或选择已保存的直接上游预览记录，点击发送一次测试请求。确认发现字段的类型后采用；样本字段名称锁定，不能改为未观察到的名称。

两种依据分别标为文档声明与样本观察。文档声明不是对服务方真实性的自动认证；样本也不能保证未来所有响应都具有同一结构。

测试返回空数组时，不会清空已有契约，也不能凭空生成字段。样本与已有契约冲突时显示具体错误，不自动覆盖契约。普通编辑不会自动调用业务 API；测试值不替换节点的正式绑定，也不自动运行上游或整套工作流。

API 预览只发起一次 GET/POST 请求，超时 20 秒，响应体上限 1 MiB，最多展示和推断 25 条记录，不追分页。上游预览记录只保存在当前画布组件的内存中，刷新页面后需重新预览。

### 上游字段与请求绑定

Body 支持对象、数组、常量、上游字段、任务参数。选择“上游字段”时，候选值来自当前连线的上游输出；选择“任务参数”时，候选值来自 Parameters 节点声明。请求属性名可以自行填写，它表示 API 请求的键，不等于来源数据字段。

Transform、Aggregate、Join 等节点继续使用编译器根据输入结构和明确规则推导输出，无需读取全部业务记录。下游应选择变换后的输出名称。失效字段保留原值并提示重新选择，后端还会检查请求体中的嵌套绑定、条件、模型输入及输出字段等引用。

## 主要代码入口

| 位置 | 本轮实现 |
|---|---|
| `src/backend/base/langflow/business/field_schema.py` | 文档与样本依据、来源绑定、发现凭据校验、响应结构导入、API 有限预览、属性存在性和字段引用检查 |
| `src/backend/base/langflow/business/connections.py` | Schema 列表、默认 Schema 归一化、SQL 空值样本类型提示 |
| `src/backend/base/langflow/business/api.py` | 按连接所属用户鉴权的 `/connections/{id}/preview` 和 `/contract`，元数据 Schema 参数 |
| `src/backend/base/langflow/business/compiler.py` | 发布前校验来源依据和引用，继续推导下游输出结构 |
| `src/backend/base/langflow/business/catalog.py` | 字段必有性声明、来源依据属性、数据库 Schema 表单格式 |
| `src/backend/base/langflow/business/sources.py` | 运行时区分属性缺失和显式 null，保留原始记录与既有问题隔离行为 |
| `src/frontend/src/pages/BusinessPage/CanvasConfiguration.tsx` | 按来源配置加载元数据，连接专用字段配置和预览组件 |
| `src/frontend/src/pages/BusinessPage/use-canvas-field-discovery.ts` | 结构检查、旧响应丢弃、上游字段和预览记录管理 |
| `src/frontend/src/pages/BusinessPage/ApiFieldConfiguration.tsx` | 契约录入/导入、独立 API 测试、样本采用 |
| `src/frontend/src/pages/BusinessPage/RequestBodyEditor.tsx` | 嵌套请求参数的常量、字段和任务参数绑定 |
| `src/frontend/src/pages/BusinessPage/DatabasePreview.tsx`、`SourceFieldEditor.tsx`、`SchemaForm.tsx` | 发现字段类型确认、真实字段下拉、属性必有/可空分别配置 |

源节点配置保存 `fields` 与 `field_evidence`；不新增数据库表。样本凭据使用现有服务密钥生成，绑定发现的列名、请求来源、连接版本和用户。手工文档契约单独记录出处，不把人工声明包装成实际采样。

## 发布、运行和既有流程

无效字段可以留在草稿供修正，但发布检查会拒绝该配置。运行使用已校验的不可变发布包，数据库运行读取继续对比实际列结构；API 在归一化之前检查属性是否存在及 null 是否允许。违反约定时保留原始依据，并沿用现有不完整数据、问题输出和按依赖隔离语义。

已有 API 或高级 SQL 配置若只有 `fields`、没有 `field_evidence`，不能直接重新发布。升级步骤：

1. 打开对应流程草稿。
2. 对 API 按真实供应方文档重新采用契约，或显式测试后采用样本字段；对 SQL 重新预览并采用结果字段。
3. 检查下游报错字段并重新绑定，保存草稿。
4. 发布新版本，再显式启用该版本。

历史发布包、任务和结果不会被改写。仅编辑无效草稿不会更改已经启用的版本；但本次部署会改变现有运行时代码摘要，依照项目既有校验规则，旧摘要的发布包需要在新运行时重新发布才能提交新任务。不能把旧字段自动补一个“已验证”标记绕过迁移。

内置新建耗材示例已使用明确标记为模拟服务的文档契约。`scripts/business/bootstrap.py` 对已有示例会从旧的不可变发布包重新校验；旧包缺少字段依据时会被拒绝，需要先完成上述迁移。不会以新模板自动覆盖用户草稿或把模拟服务契约冒充真实供应方契约。

## 验证结果

| 验证 | 结果与范围 |
|---|---|
| Business 后端回归 | **54 passed, 3 skipped**。包含发布与执行既有回归、API 实际本地 HTTP 请求、契约冲突、缺属性/可空、凭据篡改、所属用户隔离、无业务任务创建等 |
| 字段发现新增后端用例 | 上述测试中 **14 项**；包括真实 SQLite 结构反射、不同 Schema 同名表、空结果 SQL 别名与失效依据。仅将数据库连接入口替换为进程内 SQLite，不声称覆盖 MySQL/PostgreSQL 驱动 |
| 前端 Jest | **11 passed**。覆盖配置重复/节点切换、Schema 请求参数、迟到响应、API 空样本、独立测试值、样本字段锁定和嵌套请求绑定 |
| Ruff / Biome | 本轮后端功能文件和前端改动文件检查通过 |
| 全仓 TypeScript | **2026-10-12 后续修复已通过，0 条诊断**。此前 609 行日志实际包含 252 条诊断，已按 [类型修复计划](TYPECHECK-FIX-PLAN.md) 清零；历史输出保留在 `deploy/business/evidence/refactoring-20261010/typescript-baseline.txt` |
| 真实 MySQL/PostgreSQL | 未通过环境验证。Docker 服务不可用，测试端口连接被拒绝；3 项测试按既有开关默认跳过，未把 SQLite 结果充当外部数据库验证 |

本表的 Business 功能测试数字保留原功能交付时的范围；2026-10-12 后续执行的完整前端 Jest、生产构建、格式检查及 Business 后端全目录回归，以 [类型修复计划](TYPECHECK-FIX-PLAN.md) 和 [bug修复续篇](../../bug修复.md) 中的最终记录为准。

复现命令（仓库根目录）：

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python python -m pytest \
  -c deploy/business/pytest.ini deploy/business/tests -q --tb=short
```

前端命令（`src/frontend`）：

```bash
npm test -- --runInBand src/pages/BusinessPage/__tests__
./node_modules/.bin/tsc --noEmit --pretty false
```

真实测试数据库恢复后，按现有环境配置设置 `BUSINESS_REAL_DATABASES=1`，执行 `deploy/business/tests/test_databases.py`。本轮未执行浏览器端到端测试或真实业务服务部署验证。

## 当前明确限制

- 结构导入接受 JSON 文件，不接受 YAML。支持指定操作的单一成功响应、非递归本地 `$ref`、明确记录路径和扁平记录属性；有歧义的组合类型或嵌套对象字段会提示改用明确的扁平记录契约，不自动展开任意嵌套数组。
- 源码不会自动获取外部文档地址。文档出处是人工维护的引用；导入使用用户提供的 JSON 内容。
- 字段类型、可省略性和可空性仍需按实际契约确认；样本推断不是完整接口保证。
- 新增文案键已补齐 7 个语言文件。中文和英文已提供对应文案，德语、西班牙语、法语、日语、葡萄牙语的新文案暂用英文，待翻译。
