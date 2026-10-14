# 通用数据处理与业务核验平台

当前项目处于从 0 到 1 的建设阶段。按用户确认，设计变更后直接落实当前方案，不为已弃用的配置格式、节点端口或行为增加兼容分支。历史任务的保存与查询是数据管理事项，不要求继续维护弃用实现。Classification 已按此统一为当前配置和 Data／Issues 两口。

业务由画布中的节点、连线、字段绑定与配置定义。跨库对账与高值耗材使用同一个发布、任务、数据集和执行机制；高值耗材的类别及医院参数只在模板中配置。

架构改造文档：[实施方案](./REFACTORING-DESIGN.md)说明节点边界、页面配置、数据契约与验收要求；[决策记录](./REFACTORING-PLAN.md)保存已确认的 D01—D07。此次代码实现、消融对照、测试结果和真实接入限制见[改造验收记录](./REFACTORING-ACCEPTANCE.md)。[初版验收](./ACCEPTANCE.md)及[消融审查](../../spikes/001-business-architecture-ablation/README.md)保留历史范围。

## 本地启动

在 WSL（Ubuntu）或 Linux 终端中，进入已配置原项目私有环境与 Python/前端依赖的仓库根目录，启动完整项目：

```bash
bash scripts/business/start_local.sh
```

已运行的服务会复用，缺失的服务会补齐。需要重启全部项目进程时执行：

```bash
bash scripts/business/start_local.sh --restart
```

完整启动入口是 `scripts/business/start_local.sh`，它会调用底层启动脚本并启动 MySQL/PostgreSQL 模拟业务数据源。脚本会自动切换到仓库根目录，也可以在其他目录通过脚本的绝对路径调用。服务由 tmux 在后台保持，命令成功结束后可以关闭启动终端。

检查后台会话及平台日志（仓库根目录）：

```bash
tmux list-sessions
tail -n 100 deploy/verification/.cache/source-ui/langflow-platform.log
```

前置环境：Docker Desktop 已启动且对当前 WSL 启用集成；已有 `deploy/verification/.env`、专项 Python 环境、平台数据库及前端依赖。首次下载示例数据库镜像需要网络。

该命令会：

1. 启动原平台数据库，关闭通用任务的新任务受理并等待已受理任务排空；排空成功后启动或重启业务 API、模拟上游、Langflow 和前端。
2. 启动独立的 MySQL 8.4 / PostgreSQL 17 示例数据源，端口分别为 13306 / 55434，数据保存在独立 Docker 卷。
3. 在专用 `business_demo` 数据库中创建示例表。仅空表写入示例记录，不覆盖已有记录。
4. 创建缺失的示例连接与契约 v2 方案并发布；构建升级时从示例当前已启用的不可变版本重新校验发布，不用较新的未发布草稿代替。已有画布配置不会被模板覆盖。停用旧内置示例的受理入口，保留历史数据。
5. 停止旧核验入口受理新任务，检查旧任务是否结束；存在等待、运行或已经开始但需要确认的任务时暂停迁移并报出原因。被拒绝且从未开始执行的历史任务保留原状态，不阻止迁移。迁移完成后旧记录只读。
6. 确认已启用方案已按当前执行代码校验发布，恢复受理并启动 Worker。存在不满足当前契约的自建方案时保持维护状态，要求修改后重新发布或停用该方案，不自动转换弃用的 Classification 配置。正常终端启动的进程由 tmux 保持。

新数据源密码自动生成于 `deploy/verification/.cache/business-sources.env`，文件权限为 600，不打印密码。登录账号仍是 `verification-admin`，密码在原私有 `.env`。

| 页面 | 地址 |
|---|---|
| 业务方案 | http://localhost:3000/business |
| 连接管理 | http://localhost:3000/business/connections |
| 任务及动态结果 | http://localhost:3000/business/tasks |
| 旧规则和版本，只读 | http://localhost:3000/business/history |
| 旧任务、结果与证据 | http://localhost:3000/verification/tasks |

`/verification` 指向通用业务方案页。原数据库与历史结果不删除。新示例稳定编码是 `demo.cross_database.v2`、`demo.consumables.v2`；原 `demo.cross_database`、`demo.consumables` 的任务及版本仍可查看，但停止接收新任务。历史记录没有新版覆盖评估时显示“未评估”，不追认成已通过。

当前环境的 WSL Docker 套接字不可用时，脚本会尝试 Docker Desktop 的 Windows CLI。复用旧 PostgreSQL 时，先确认原数据卷已经初始化，再去掉仅首次初始化需要的失效绑定挂载；不会创建一个空库替换原数据。

## 配置与使用

1. 管理员在连接管理登记 MySQL、PostgreSQL、API 或模型连接。凭据加密存储；画布与发布包只引用连接标识。数据库可以读取表、视图和最多 25 行的预览。
2. 在业务方案选择起始模板，输入名称和稳定编码，勾选允许调用的外部来源。名称供人识别，稳定编码供接口选择方案。
3. 打开画布、选择节点，在右侧“业务配置”面板修改。字段下拉来自上游结构。数据库读取节点选择连接和表；高级 SQL 使用命名参数，如 `:start`，配置参数名称列表，并通过预览建立、确认输出字段类型。
4. 用任务参数节点定义外部系统可以提交的参数。外部请求不能覆盖节点的数据库连接或 SQL。
5. 在 Validate 节点配置业务身份的名称、来源命名空间、身份字段。配置主 Output 的“结果交代约定”：普通处理可以仅输出清单；核验模式引用原始读取节点、身份定义、核验单元和各事项结果端口，以及范围外和无法比较的去向。问题分支也可连接其他 Output，所有原始与中间数据集仍可查看。
6. 等待画布自动保存，返回业务方案，点击“检查并发布已保存画布”，然后启用该版本。
7. 通过“联调提交任务”或公共 API 提交。任务受理时固定发布版本，后续修改画布或启用其他版本不改变已受理任务的配置。
8. 在任务详情查看执行状态、逐明细去向、按核验单元统计的各事项结果、覆盖缺口、来源完整性与模型请求记录。点击事项查看该事项的单元结论；通过数据集下拉查看原始快照、成员关系及问题分支。表格每页最多 200 行，页面默认 50 行。

“执行完成”表示流程执行结束，不表示全部获得有效业务结论。“已交代”表示已收到的原始记录都有结果或明确去向，其中仍可能有未比较。来源完整性另外展示，不把收到的记录全有去向当成来源已全部取得。旧的问题数量仍按节点累计；新的覆盖区按声明的业务身份和事项统计。

### 两个示例

**跨数据库对账**：MySQL 的 `orders` 保存 O001=100、O002=200、O003=300；PostgreSQL 的 `payments` 保存 O001 两笔合计100、O002=180、O004=50。流程校验、分组求和、全关联、比较，得到相同、不同、仅订单、仅付款四类结果。O002 的付款减订单为 -20。连接或字段名改变时，在画布重新选择并发布。

**高值耗材模拟**：通过 API 读取结算与分类目录，区分医保/耗材事实、关联目录、筛选目标类别、建立业务单元，再依次取得检查、序列、影像清单，调用专业适配，分别比较类别、数量、费用。髋/膝及比较前提均配置在模板中。默认 `scenario=baseline`；模拟专用 `scenario=adversarial` 提供 18 次原始出现，包含重复、冲突、缺身份、无影像、非法数量、计量范围不明及混合单价等反例。类别和数量可比较而费用不具备条件时，仅费用未比较。专业观察响应独立于结算期待数量，带 `simulated=true`；当前没有读取真实 DICOM 或证明真实识别效果。

## 节点能力与约定

首期节点：任务参数、数据库读取、API 读取、文件读取、字段转换、数据校验、条件分流、关联、汇总、字段比较、模型分析、数据合并、结果输出、子流程。另有可选的专业影像适配组件。

- 数据库：SQLAlchemy `yield_per` / `fetchmany(5000)`；MySQL、PostgreSQL 读取事务限制写操作。复杂 SQL 仅允许单个 SELECT/CTE，仍由数据库只读事务执行约束。
- API：支持 GET/POST、页码/游标/无分页；请求体中 `{"parameter":"hospital"}` 绑定任务参数，`{"field":"patient_id"}` 绑定上游记录。连接了数据集时逐条请求。响应声明字段供下游绑定，完整记录保留在 `_raw_record`；逐条请求另保留 `_request_row_id`。配置 `completeness` 的范围和依据，必要时绑定响应完整性字段；没有依据时保持未知。逐对象独立范围的失败保留问题并继续其他对象，共享范围读取不完整则阻断依赖其完整性的结论。
- 文件：CSV（UTF-8）、JSON、Parquet，上传上限 100 MB；更大数据建议数据库分批读取。文件预览不能证明所有记录结构相同。
- 转换：复制/重命名、类型转换、值映射、受限算术表达式；原始快照保留。需要明确检查转换后空值时，连接数据校验节点。
- 校验与分流：校验输出合格/问题/重复关系。同身份的全部原始事实一致时只参与一次计算，原始出现全部保留；事实冲突全部进入问题，身份缺失不相互合并。分流输出满足/不满足/未知。缺失事实不能自动归为范围外。
- 关联：指定两侧业务键和基数关系。重复键冲突和空键进入问题分支，也保留受冲突影响的对侧记录。单侧记录不补零。
- 汇总：跨批次在 DuckDB 中完成，额外输出分组与来源行对应数据集。依赖成员转换失败、身份冲突或数量缺失时，不将剩余有效成员的局部合计当成完整总量；影响范围不明时保守阻断。`collect` 可生成证据清单。
- 比较：精确相等、带容差的数值比较、忽略大小写。输出单项比较、差值、总状态。空值、单侧缺失和值不同分开表示。
- 模型：只发送配置的输入字段；每次请求发送前持久登记，保存输入、结构化输出、原始响应与状态。持久登记失败不发送；超时保留远端未知，HTTP 202 保留已受理但未确认完成，不自动重提。模型输出是观察结果，结构合法仍需业务比较前提。首期调用器支持同步结果，真实异步查询协议需适配后验收。
- 合并：Union 负责追加和字段对齐；旧 `deduplicate=true` 拒绝发布并要求迁移到下游 Validate 的身份配置，避免两处定义重复规则。
- 子流程：选择已发布版本，绑定参数及一个结果输出。子流程的任务参数节点可声明输入数据字段。发布父流程时校验结构并复制依赖包。
- 插件：Python entry point `langflow.business_nodes` 返回 `NodePlugin`，提供表单结构、输出字段、执行函数与 Langflow 组件。新算法通过组件扩展；平台核心不按医院/订单/耗材名称选择路径。

## 数据与版本

元数据位于原业务数据库新增的 `business_*` 表。原始/派生数据位于 `BUSINESS_DATA_DIR`，默认 `deploy/verification/.cache/business-data`。节点之间传递数据集引用，不传百万行 JSON。DuckDB 默认每个运算内存限制 512 MB、2 线程，临时文件落在任务目录；整个进程内存不等于 DuckDB 单连接限额。

“全量原始字段”指配置的查询返回的全部字段。SQL 只选择三列就只能保存三列。字段投影与筛选不会删除已封存原始快照。结果通过父数据集、行标识、关联侧标识及分组成员数据集追溯。

每个数据源独立取数，不能声称跨 MySQL/PostgreSQL 具有同一全局事务快照。发布版本固定节点配置、连接元数据、字段结构、参数、子流程和执行依赖指纹。已绑定字段消失或类型变化会报错；新增未绑定的数据库列会保存在原始数据中。执行依赖变化需要重新发布，纯演示、文档和页面文件不影响执行指纹。中断且缺失完成凭据的任务需要人工确认，不自动重复模型调用。

升级前在业务方案页面关闭新任务受理并等待排空，然后更换执行构建。发布版本提供“按此版本配置重新校验发布”，使用所选历史配置；含子流程时先升级子版本，再明确调整父流程绑定。不能把正在运行的服务直接切换到新代码后，再期待排空机制恢复旧环境。

## 外部系统接口

公共 API 在业务 API 服务，端口取 `.env` 的 `VERIFICATION_SOURCE_API_PORT`（当前配置通常为18081）。管理页面经 Langflow 的已登录管理员接口转发。不同来源使用各自的 Bearer 令牌，来源不能从请求体伪造。

```http
GET /api/v1/business/schemes
Authorization: Bearer <该来源令牌>
```

返回该来源有权调用的方案编码、名称、启用版本、输入参数及结果结构。

```http
POST /api/v1/business/tasks
Authorization: Bearer <该来源令牌>
Idempotency-Key: your-unique-request-id
Content-Type: application/json

{"scheme":"demo.consumables.v2","parameters":{"hospital":"synthetic-hospital","start":"2024-01-01","end":"2027-01-01"}}
```

查询：`GET /api/v1/business/tasks`、`GET /api/v1/business/tasks/{id}`、`GET /api/v1/business/tasks/{id}/datasets/{dataset_id}?limit=50&offset=0`。相同来源同一幂等键只能对应相同请求；未授权任务返回404。

任务详情的 `assessment` 给出覆盖状态、原始出现数、业务身份数、缺失身份数、各事项的单元结果与数据集引用。请求记录通过 `GET /api/v1/business/tasks/{id}/requests` 及 `/{request_id}` 查看，同样按任务来源隔离。没有覆盖声明的普通处理返回 `mode=ordinary`，没有新版评估的历史任务返回 `state=unassessed`。

## 验证命令

```bash
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python -m pytest -c deploy/business/pytest.ini deploy/business/tests -q

# Docker 示例源已启动后，执行真实 MySQL/PostgreSQL 验证
BUSINESS_REAL_DATABASES=1 UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python -m pytest -c deploy/business/pytest.ini deploy/business/tests/test_databases.py -q

# 百万行 Parquet 输入、实际 Langflow Graph 执行
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/benchmark.py

# 百万行真实 MySQL/PostgreSQL 读取；在两个示例库中使用独立临时测试表
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/benchmark.py --databases --output deploy/verification/.cache/business-database-benchmark.json

# 独立全栈测试，临时 SQLite 元数据、真实 HTTP、模拟业务 API、Chromium
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/smoke.py

# 已启动的实际项目：提交两条新任务，检查 Worker、结果、来源隔离和旧数据数量
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/verify_local.py

# 已启动的实际项目：提交一条模拟反例任务，检查维护状态、结果／请求页及画布责任配置
# 可用 --task <已有反例任务 ID> 复用记录；不会启用默认 Playwright 的数据库清理流程
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/business/verify_browser.py
```

浏览器不在 Playwright 默认路径时，可设置 `BUSINESS_CHROMIUM_EXECUTABLE` 指向已安装 Chromium；首次安装可在前端目录执行 `npx playwright install chromium`。独立全栈测试日志与截图放在 `/tmp/business-smoke-*`；`verify_browser.py` 截图放在 `deploy/verification/.cache/business-browser-acceptance`，新增的模拟任务保留供页面查看。浏览器验收对外部模板商店标签返回空夹具，业务 API 和结果均使用真实本地服务。

`benchmark.py --databases` 的计时包括任务执行与临时表清理，不包括准备测试数据；峰值内存是整个测试进程的峰值，不是只统计 DuckDB。`verify_local.py` 会在当前项目留下两条可在页面查看的验收任务。

前端新增文案提供中文和英文，另外五个已有语言使用英文回退文案，尚未进行人工翻译。专业真实模型、真实目录来源和源数据库授权需要实际连接配置；本仓库示例不冒充这些真实能力。

当前髋膝核心画布已升级为 11 节点，支持 DR／CT、EXAM_PART 标准字典与检查适用性判断。见 [实施与验收记录](STUDY-RELEVANCE-IMPLEMENTATION.md)。
