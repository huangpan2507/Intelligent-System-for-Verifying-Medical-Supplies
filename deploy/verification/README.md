# 高值耗材范围核验：源码运行与规则发布

当前实现使用合成结算、影像和识别服务，验证业务链路，不识别真实 DICOM，也不需要大模型 API key。监管端只提交医院范围、医保结算时间范围、规则名称或编码；具体筛选、关联及比较规则在 Langflow 中保存、发布和启用。

## 从源码启动

已完成配置的当前环境，在 WSL／Linux 终端执行以下一条命令即可启动完整模拟项目：

```bash
bash /home/huangpan/github_repo/langflow/scripts/verification/start_local.sh
```

需要重启所有应用进程时执行：

```bash
bash /home/huangpan/github_repo/langflow/scripts/verification/start_local.sh --restart
```

脚本自动定位仓库目录，复用已有私有配置、Python 环境、前端依赖和数据库。在当前 Windows/WSL 环境中会自动启动 Docker Desktop，等待 PostgreSQL 就绪，再启动旧模拟上游、新Business核心流程模拟API、核验 API、平台后端、唯一 Worker 和前端，并检查 HTTP 服务与前端代理。重复执行普通启动命令会复用已启动进程；`--restart` 会先停止本脚本管理的应用进程，再启动，PostgreSQL 继续复用。重启会中断正在执行的任务，请在任务完成后使用。

进程保存在独立 `tmux` 会话中，关闭当前终端后仍会运行；主机／WSL 重启后重新执行启动命令即可。启动脚本不会重新生成凭据、初始化业务数据、导入流程、发布规则或提交模拟任务。前端入口：<http://localhost:3000/verification/tasks>；日志位于 `deploy/verification/.cache/source-ui/langflow-*.log`，可用 `tmux ls` 查看进程会话。

以下为首次配置和手工启动说明。启动脚本要求已有 `uv`、Node/npm、`tmux`、Docker Compose，以及配置好的专项运行环境；它不替代首次依赖安装和流程发布。

仓库根目录执行。专项 Python 环境位于 `deploy/verification/.cache/runtime`，重建依赖见 `requirements-source.txt`。以下命令统一通过 `uv run` 使用该环境；已有私有 `.env` 时不要再次执行 `configure_demo.py`。

```bash
# 首次配置才执行，生成私有凭据，不覆盖已有文件
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/configure_demo.py

# 本项目独立 PostgreSQL；端口 55433，不使用其他项目的 55432
# 使用已经验证的镜像摘要；本机已有该镜像时可加 --pull never
docker compose -f deploy/verification/compose.yaml -f deploy/verification/compose.source.yaml up -d --no-build postgres

# 建立新范围契约 schema 和模拟医院、独立病例核实记录
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/run_local.py init
```

下面每项在独立终端运行，保持终端运行：

```bash
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/run_local.py platform
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/run_local.py api
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/run_local.py demo
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/run_local.py core-demo
cd src/frontend
npm run start -- --host 127.0.0.1 --port 3000 --strictPort
```

- 前端：<http://127.0.0.1:3000/verification>，顶部“核验规则”按钮。
- Langflow 平台 API：7860；业务 API 默认 8081，可由私有 `.env` 的 `VERIFICATION_SOURCE_API_PORT` 指定；旧模拟上游：8090；本轮Business核心流程模拟API：8091（独立tmux会话`langflow-business-core-demo`）。本机当前配置为 `18081`，业务接口文档：<http://127.0.0.1:18081/docs>。
- 登录 `verification-admin`，密码为私有 `deploy/verification/.env` 的 `LANGFLOW_SUPERUSER_PASSWORD`。
- 业务库使用 `verification_scope` schema。初始化器拒绝旧试验表；不提供旧 `detail_ids` 任务契约兼容。源码平台继续使用 `.cache/source-ui/langflow.db`，保留用户画布。

WSL／主机重启后，源码进程会退出，需要重新启动。先启动 Docker Desktop，并执行上述 Compose 命令恢复本项目 PostgreSQL，再启动平台、业务 API、模拟上游和前端。已有数据库无需重新初始化或重新导入流程。端口 8081 若被其他项目占用，在私有 `.env` 中设置 `VERIFICATION_SOURCE_API_PORT=18081`，随后重新启动平台、业务 API 和 Worker；三个进程及模拟提交／验收脚本读取同一配置，`submit_demo.py --url` 仍可显式覆盖。此配置仅用于源码进程，不改变 Compose 内部服务端口。

## 保存草稿、发布与启用

平台启动后生成并导入新的十节点草稿：

```bash
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/build_flow.py
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/import_flow.py
```

导入脚本记录 `VERIFICATION_DRAFT_FLOW_ID`，并在需要时创建 Worker API key。该 ID 仅供编辑选图；Worker 不按它执行可变草稿。如果换了平台数据库，原 API key 不能复用，需在私有配置中清空后重新导入。

1. 打开“核验规则”，登记名称 `高值耗材智能体`、稳定编码 `high_value_consumables`，选择导入的草稿。
2. 点击“编辑草稿”，在原画布配置 01/02/03/04/05/06/07。画布沿用 Langflow 自动保存；原生版本历史的 Save 是编辑历史，不是业务发布。
3. 返回规则管理页配置耗材目录映射，点击“保存规则草稿”。目录和发布说明会落库，刷新可重新读取；并发覆盖会被拒绝。`DEMO-HIP`、`DEMO-KNEE` 仅为合成样本。
4. 点击“校验已保存草稿”。平台读取已经保存的画布，检查节点、端口、连线、参数、依赖及运行构建，并在隔离临时库实际执行候选图的完整模拟链路。
5. 校验通过后“发布版本”，生成包含完整图、节点配置、目录、接口与构建摘要的不可变发布包。校验以后又改草稿，不会改变这个候选；需重新校验才会发布新内容。
6. 在“已发布版本”中“启用此版本”。发布和启用是两步；仅启用后才能接受新任务。切换/停用不改变已经受理的 Run。查看已发布版本为只读，选择节点可检查参数。

本期管理页面要求平台管理员，并检查规则与草稿的所属用户；不开放监管来源修改规则。已发布模拟版本不能用于正式运行。修改执行源码或依赖后须重启平台和业务 API；旧发布包若缺匹配运行构建会拒绝执行，不能回退到新源码。当前只配置一个运行构建，尚不提供多个旧构建的部署路由。

## 提交完整模拟

启用规则后启动唯一 Worker：

```bash
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/run_local.py worker
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python scripts/verification/submit_demo.py --reference scope-demo-001 --output-dir deploy/verification/.cache/demo-runs
```

脚本向配置的源码业务端口发出以下业务体，使用模拟监管 Bearer token。`Idempotency-Key: scope-demo-001` 是传输层请求去重编号，不是第四项业务规则配置。

```json
{
  "hospital_scope": "常州市第一人民医院",
  "settlement_time_range": {
    "start_inclusive": "2024-06-01T00:00:00+08:00",
    "end_exclusive": "2025-09-01T00:00:00+08:00"
  },
  "rule": "高值耗材智能体"
}
```

时间为左闭右开，覆盖 2024 年 6 月至 2025 年 8 月底的医保结算。任务不会扩大到范围外的结算；03 的检查窗口只决定选中结算的关联依据。医院字符串按平台医院映射精确解析，并检查监管来源允许的医院；模拟医院映射在 `demo.seed_demo()`，真实机构映射仍待接入。

同来源、同编号、同内容重复提交返回原任务；异内容返回 409。受理事务固定 `release_id / binding_id / job_id`；Worker 提交持久 Job，按发布包构图，节点间只传运行引用及统计。Job 成功与 08 业务落库回执分别验证，不以 HTTP 成功代替结果成功。

默认合成范围含三条结算、两个核验单元：髋关节两条同价明细合计 2 套，识别 1 套，数量差 −1、费用折算差 −10000；膝关节一致。测试将 01 每页条数设为 1，验证髋明细跨页仍只调用一次模型。差异仅供复核，不等于骗保或基金损失认定。

查询结果和证据均按 `run_id` 固定，不触发执行：

- `GET /api/v1/verification/tasks/{task_id}`：状态、阶段、版本、分页和单元进度。
- `GET /tasks/{task_id}/results?run_id=…&limit=…&offset=…`：汇总及结果分页。
- `GET /tasks/{task_id}/evidence?run_id=…&limit=…&offset=…`：工件和请求证据分页（完整前缀同上）。
- `POST /tasks/{task_id}/runs`：人工确认旧执行已结束后新建 Run；默认沿用原发布版本、环境和封存结算快照。未封存快照须明确 `refetch_unsealed: true`。改变医院、时间或采用新启用版本应新建任务。

`submit_demo.py` 导出的是本次查询页，超过默认页大小时应使用分页 API 获取后续页。模型超时/中断进入待确认，不自动重提；Job 失联可重新查询同一登记，不创建第二个执行。

## 在页面中查看任务与结果

登录平台管理员后，点击顶部“核验任务”，或打开 <http://127.0.0.1:3000/verification/tasks>。规则管理页也提供同名入口。

- 任务列表支持按任务编号、任务 ID、医院或规则搜索，按执行状态筛选，每页 20 条，状态每 5 秒自动刷新。
- 点击任务编号查看医院、结算时间范围、固定规则版本、当前阶段、结果汇总和明细。数量、金额的结算值、识别／折算值和差值分别展示；缺失数据不会显示为零。
- “查看依据”展示结算明细编号、核实范围依据、识别请求和未比较原因。“证据”页签分页展示阶段工件和模型请求，可在页面内展开原始数据。
- “运行历史”可切换已有 Run。详情链接中的 `run_id` 固定到该次运行，后续重跑不会替换这个链接展示的结果。查看页面只读取已保存数据，不创建任务、不触发识别。
- “已完成”描述执行状态；存在差异、未比较和一致属于业务结论。失败或待确认的运行明确显示状态及错误，尚无结果时不会显示为核验通过。

平台页面使用现有登录态，前端不接收业务服务令牌。平台管理员只可查看自己规则下的任务；监管来源仍只能查看自己提交的任务。中文和英文界面已提供，其他五种语言暂使用对应英文文案。

## 监管系统结果查询接口

监管端对接已有系统，使用自己的 Bearer token 调用核验业务 API（本机配置为 <http://127.0.0.1:18081/docs>），无需访问平台管理接口。以下路径前缀均为 `/api/v1/verification`：

| 方法与路径 | 用途 |
|---|---|
| `GET /tasks?status=completed&q=医院或任务编号&limit=20&offset=0` | 查询本来源的任务列表，返回 `items / total / limit / offset`；按任务受理时间倒序 |
| `GET /tasks/{task_id}` | 查询最新运行状态；指定 `run_id` 时查看该历史运行 |
| `GET /tasks/{task_id}/runs?limit=20&offset=0` | 分页查询运行历史，最新运行在前 |
| `GET /tasks/{task_id}/results?run_id=…&limit=20&offset=0` | 查询指定运行的汇总和结果明细；汇总针对全量结果，`results` 是当前页 |
| `GET /tasks/{task_id}/evidence?run_id=…&limit=20&offset=0` | 查询阶段工件和识别请求；`pagination.artifacts_total`、`model_requests_total` 分别给出两个集合的总数 |

`status` 可取 `waiting / running / completed / partial_failed / failed / needs_confirmation`；`q` 最长 200 字符，可匹配任务 ID、外部编号、医院和规则。分页 `limit` 最大 200、`offset` 不小于 0。证据接口对两个集合分别应用同一组分页参数，某个集合的后续页可能为空；应依据各自总数判断是否取完。

列表和详情的来源身份由服务端根据令牌确定，不接受客户端指定另一监管来源。跨来源访问任务、历史、结果或证据返回 404。推荐监管端先查询任务状态，记录对应 `run_id`，随后用同一个 `run_id` 查询结果与证据，避免重跑期间混读两个 Run。

监管端展示结果时使用以下字段：

| 字段 | 展示语义 |
|---|---|
| `status / stage / error` | 执行状态、当前阶段及失败原因；`completed` 不等于所有核验单元一致 |
| `available / result` | 是否已保存结果；`available=false` 时 `result=null`，展示处理中或未产出结果 |
| `rule_version / release_id / run_id` | 本次结果实际采用的规则版本和运行标识 |
| `result.simulated` | 是否为模拟数据，应在页面显著标识 |
| `result.summary` | 全量结算条数、核验单元数、一致、差异、未比较、失败等数量 |
| `result.results[].conclusion` | `consistent / difference / not_compared`：一致、存在差异、未比较 |
| `quantity.settlement / recognized / delta` | 结算数量、识别数量、差值及 `unit`；十进制值使用字符串传输 |
| `fee.source_amount / converted_amount / delta` | 结算金额、按识别数量折算的金额、差值及 `currency` |
| `type / quantity / fee` 下的 `status / reasons` | 各比较项的结论和未比较原因；`not_requested` 表示本版本未要求该比较项 |
| `detail_ids / request_id / review_evidence` | 对应结算明细、识别请求及核实范围依据，可用于详情追溯 |

数量或金额缺失、未比较时显示“未比较／缺少依据”，不能将 `null` 当作零。金额差值为折算金额减结算金额，只作为复核线索。显示差异明细后，可通过证据接口的 `model_requests[].request_id` 找到对应的原始识别响应；阶段证据在 `artifacts[]` 中按 `kind` 区分。

## 节点职责与配置

左侧 Components → Verification 提供任务输入和 00—08，共十个独立组件；不存在旧通用阶段组件。

| 节点 | 业务职责与参数 |
|---|---|
| 任务输入 | Worker 提供 task_id、run_id、release_id、job_id；这些不是用户固定填写的规则 |
| 00 任务入口校验 | 检查任务/运行/Job、领取状态、固定发布版本与模式，输出引用上下文 |
| 01 结算快照 | 范围查询 API URL（POST）、每页条数；校验边界和游标、去重、封存源快照；重跑复用封存快照 |
| 02 耗材筛选 | 字段/运算符/值、多条件 AND/OR、缺值策略；整份封存快照跨页分组，保留排除原因 |
| 03 检查关联 | 检查列表 URL（GET）、结算前后天数、DR/CT；患者/医院/就诊及时间匹配，取得 study_primary_id |
| 04 部位初筛 | 部位/项目名称字段及词表，未知仍待核实 |
| 05 影像清单 | 序列 URL、影像 URL，study_primary_id → series_id → DICOM 下载地址；只存清单 |
| 06 模型识别 | 模型 URL（POST）；先登记请求，再调用，保存原始响应 |
| 07 确定性比较 | 比较项目、数量/金额容差；事实依据、单位/计数范围/同价等条件必须满足 |
| 08 结果保存 | 检查所有快照明细由终态单元覆盖，事务保存汇总及运行完成状态；空范围明确记录 |

本机默认 URL：01 `http://127.0.0.1:8090/v1/settlements/query`；03 `…/api/v2/study/list`；05 `…/api/v2/dicom/series-instance-uid?study_primary_id={study_primary_id}` 及 `…/api/v2/storage/dicom/sop-instance-uid?series_id={series_id}`；06 `…/v1/recognitions`。以画布中字段和发布检查解析的实际 URL 为准，不提供 cURL。

03/05 影像云三接口的具体契约见 [imaging-api-contract.md](imaging-api-contract.md)。凭据在部署环境，发布包不内嵌密钥；凭据只发送到配置服务的同源 URL。01/06 真实厂商契约和正式验收未具备，当前发布检查只允许模拟模式。

每页结算最多 200 条，一个核验单元最多 100 条结算，超限明确停止，不拆开计数范围。03—07 一次加载一个单元，结果/证据分页读取。本期未完成大范围压测、多 Worker 或逐节点自动续跑。

## 验证与部署边界

```bash
uv run --no-project --python deploy/verification/.cache/runtime/bin/python python -m pytest -c deploy/verification/pytest.ini deploy/verification/tests -q
# PostgreSQL 并发测试另需 VERIFICATION_TEST_POSTGRES_URL；未设置时该项明确跳过。
cd src/frontend
VERIFICATION_E2E=1 npx playwright test --config playwright.verification.config.ts
```

浏览器专项使用独立配置，无删除用户流程的全局清理；需要已运行模拟服务、已导入草稿及可用 Chromium，可用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 指定。每次登记独立测试规则，测试数据保留供检查。

Compose 全量运行可使用 `compose.yaml` 构建本仓库源码并启动业务服务；内部 API 仍为 8080，宿主暴露 8081。不要替换成未包含改造的旧镜像。本轮验证以源码多进程和独立 PostgreSQL 为准；整镜像构建、真实厂商接口、算法效果、峰值容量与现场正式部署仍待验收。具体状态见根目录 plan.md / progress.md / finding.md。
