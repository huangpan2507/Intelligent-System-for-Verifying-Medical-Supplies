# 高值耗材核验：本期模拟联调

这套改造在现有 Langflow 1.12.0 源码上增加独立核验 API、单 Worker、01—08 画布流程及模拟上游。业务页面由原监管系统承接。任务、结算快照、影像引用、模型请求、原始结果和比较结果均保存到业务数据库，平台执行日志不作为结果替代品。

模拟服务使用合成患者与虚构 DICOM 地址，不下载或识别真实 DICOM。结果中 `simulated: true`、模型版本和证据引用明确标记模拟。它验证工程链路，不能证明真实识别或跨影像计数效果。

本期流程没有调用大模型，也不需要大模型厂商的API key。报告§7.4.1将大模型文本解析列为后期可选能力，本期默认使用规则。06节点调用的是模拟影像识别HTTP服务，返回预设数量；07节点执行确定性比较。`VERIFICATION_LANGFLOW_API_KEY`是Worker调用本地Langflow的凭据，由平台生成，与模型厂商密钥不同。

项目计划、进度、发现分别见仓库根目录 `plan.md`、`progress.md`、`finding.md`。实际验证范围和限制以 `progress.md` 最新记录为准。

## 目录与职责

| 位置 | 作用 |
|---|---|
| `src/backend/base/langflow/verification/api.py` | 任务受理、来源鉴权、状态/结果/证据查询、人工确认和重跑、内部保存回执 |
| `database.py` | 独立业务schema、唯一约束、短事务领取、不可变结果与证据 |
| `worker.py` | 仅领取waiting，调用固定flow_id，检查已持久化的终态 |
| `schemas.py` / `settings.py` | v1输入契约、缺失字段表达和运行配置 |
| `pipeline.py` / `rules.py` | 01—08阶段操作及确定性比较规则的单一实现 |
| `demo.py` | 模拟结算、影像云和同步识别契约 |
| `src/backend/base/langflow/verification/components.py` | 共享的业务节点参数和执行适配 |
| `components/verification/` | 任务输入和00—08独立可拖拽组件 |
| `consumable-verification-palette.json` | 默认导入流程，使用Verification独立组件组装 |
| `scripts/verification/` | 凭据初始化、流程生成/导入、任务提交示例 |
| `tests/` | 独立业务服务测试及当前Langflow Graph集成测试 |

01—08仍由画布依赖推进。独立组件共享受理上下文校验、固定契约HTTP调用与业务规则，避免复制鉴权、请求登记和回执判断。组件职责固定，无需选择阶段编号；02—07直接显示对应的业务参数或HTTP URL。03/05/06支持画布覆盖接口地址，留空使用部署默认值；凭据来自部署环境，监管提交任务不能选择URL、SQL或flow_id。本期没有逐节点恢复；阶段状态是审计记录，已开始的阶段不能自动重启。

## 从Verification拖拽搭建流程

源码后端加载`deploy/verification/components`后，刷新浏览器，展开 **Components → Verification**。该分类与Input & Output、Data Sources等通用分类分开，默认包含以下10个入口：

`Chat Input 任务输入 → 00 任务入口校验 → 01 结算快照 → 02 耗材筛选 → 03 检查关联 → 04 部位初筛 → 05 影像清单 → 06 模型识别 → 07 确定性比较 → 08 结果保存`

新建空白流程，从该分类拖出每个节点，按上述顺序连接：输入节点的“任务消息”连接00的“核验上下文”，随后各阶段的输出连接下一阶段的“核验上下文”。拖出02即可编辑筛选条件，拖出07即可配置比较项目，不需要编辑代码或选择Business Stage。组件也支持双击添加。

这些节点是本项目新增的业务组件，具有独立类型，例如`VerificationConsumableFilter`和`VerificationResultComparison`。它们继承内部基类`VerificationStageComponent`，使用Langflow原生Component、输入控件、端口和图执行机制，共用后台Pipeline。内部基类不注册为可拖拽入口。原内置Chat Input仍保留在原分类；Verification里的任务输入专门传递核验JSON，不提供聊天模型或聊天记录功能。

本项目处于从0到1阶段：早期通用节点`ConsumableVerificationStage`及其兼容入口、旧流程导出、迁移脚本已删除，不再维护两套节点形式。后续正式规则发布的不可变版本、任务绑定和审计属于业务能力，仍按范围任务设计实施。

搭建与执行是两步。新画布保存后，若要让业务API/Worker执行它，将私有`deploy/verification/.env`中的`VERIFICATION_FLOW_ID`设为新流程URL中的UUID；确认没有进行中的任务后，重启业务API和唯一Worker以加载绑定，再用新`--reference`提交模拟任务。平台账号/API key无需更换。本次没有自动替换原流程绑定。

任务输入必须包含已受理、已领取运行的`task_id`、`run_id`、`detail_ids`。空输入或聊天文字无法启动业务核验；00节点会给出明确JSON格式提示。默认由Worker填充，Worker使用`input_type=any`将数据传给输入节点。调用平台运行API时也使用`input_type=any`。本期仍要求完整00—08顺序，不能跳过保存或重复执行已开始的阶段。

本机已保存从空白画布实际拖拽并连线的“Verification 拖拽搭建示例”；未切换生产绑定。也可以生成独立组件版JSON后通过项目页导入：

```bash
uv run python scripts/verification/build_flow.py
```

输出为`deploy/verification/consumable-verification-palette.json`，也是`import_flow.py`的默认导入文件；生成器只提供这一种流程。后端修改组件代码后需重启，已保存画布的嵌入组件代码也需要同步更新；仅刷新前端不能替代后端组件目录重新加载。

## 在节点上配置业务规则

当前流程使用任务输入和九个独立业务节点，没有LLM节点。`核验上下文`是连线传递的数据。工具栏的`Parameters`用于控制参数可见性/API输入；实际业务配置在节点上的表格、下拉框和数值输入中填写。

| 节点 | 业务职责 | 当前配置入口 |
|---|---|---|
| Chat Input / 00 | 承载并校验已受理任务的入口数据 | Worker传入task_id、run_id、detail_ids |
| 01 结算快照 | 按明细编号查询并保存结算数据 | 使用部署配置中的结算接口 |
| 02 耗材筛选 | 对规范化结算字段应用附加条件 | 筛选字段、运算符、目标值；AND/OR；缺值处理 |
| 03 检查关联 | 查询并核对同患者、医院、就诊的检查 | 检查列表URL（GET）；结算前/后天数；DR/CT多选 |
| 04 部位初筛 | 用文本字段与类别词表筛查检查 | 部位/项目名称字段；髋、膝、明确无关词表 |
| 05 影像清单 | 查询影像引用并保存清单 | 序列查询URL（GET）、影像查询URL（GET） |
| 06 模型识别 | 登记请求、调用识别服务、保存原始响应 | 模型API URL（POST） |
| 07 确定性比较 | 比较种类、数量及按结算单价折算的费用 | 比较项目多选；数量/金额绝对差容差 |
| 08 结果保存 | 原子保存结果及完成状态 | 固定业务保存协议 |

**02示例：只让数量至少2的明细继续识别。** 点击节点内“配置筛选条件”，双击表格单元格，选择“数量（quantity）→大于等于→2”，点击弹窗“Save/保存”，等待流程自动保存。可新增多行条件，选择“全部满足（AND）”或“任一满足（OR）”。文本支持等于、包含及列表匹配；列表用英文逗号分隔，布尔值填`true/false`，有值/缺失不需要目标值。无附加条件时只保留固定基础筛选。字段来自当前结算契约，不支持任意SQL或表达式。

默认演示配置是数量≥0；改为≥2后，合成髋样本（2套）继续识别，膝样本（1套）保留排除原因、不调用识别服务。提交任务需使用新的`--reference`；相同编号只查询旧结果，不会用新规则重算。多明细属于同一已核实计数范围时，其中一条被排除会阻断该范围的比较，不重新拼凑范围。

**07示例：只比较数量，并允许绝对差1。** “比较项目”只选“数量”，“数量绝对差容差”设为1；髋样本差值仍保存为−1，但数量结论按该容差视为一致，未选种类/费用标记`not_requested`。数量与费用的种类对齐、人工核实范围、计数单位及证据前提仍然检查；取消种类输出不会绕过这些前提。

参数优先级：03画布时间窗优先于任务提交中的同名值；03/05/06非空URL优先于部署默认地址；07画布金额容差用于源金额校验及费用比较，覆盖本次执行中的部署默认值。实际生效配置写入02/03/04/05的工件和07比较结果的`node_configurations`/`comparison_rules`，每条筛选条件记录实际字段值与命中情况。修改画布影响之后执行的任务，不改变已保存结果。当前尚未在受理时锁定整份流程配置快照。

### 配置03/05/06的HTTP接口

影像云有三个GET接口：03查询检查列表，04对关联检查作部位筛查，05用筛查后的检查主键查序列，再用序列主键查影像下载地址。06另行POST模型接口。直接在节点上填写完整URL，不提供cURL。

| 输入框 | 本机模拟服务示例 |
|---|---|
| 03 检查列表 URL（GET） | `http://127.0.0.1:8090/api/v2/study/list` |
| 05 序列查询 URL（GET） | `http://127.0.0.1:8090/api/v2/dicom/series-instance-uid?study_primary_id={study_primary_id}` |
| 05 影像查询 URL（GET） | `http://127.0.0.1:8090/api/v2/storage/dicom/sop-instance-uid?series_id={series_id}` |
| 06 模型 API URL（POST） | `http://127.0.0.1:8090/v1/recognitions` |

03的患者、医院、就诊、时间窗和模态查询参数自动生成。05替换`{study_primary_id}`及`{series_id}`；影像URL可追加`&url_type=4`等地址类型参数。06使用所填URL，不自动追加路径；请求体由核验上下文生成。完整字段映射、三个原始文档链接和鉴权规则见[影像云接口说明](imaging-api-contract.md)。

留空时03/05使用`VERIFICATION_IMAGING_URL`加对应文档路径，06使用`VERIFICATION_MODEL_URL`加`/v1/recognitions`。手工配置影像URL时使用上表三个v2接口。实际地址写入结果的`node_configurations`，检查/影像工件也保存对应配置。

影像鉴权使用`VERIFICATION_IMAGING_TOKEN`作为`X-Token`；本机模拟模式下未单独配置时可使用本地生成的模拟token。06仍使用部署上游Bearer token。凭据仅发送到各自部署服务的同源URL，自定义跨源URL不自动继承凭据。接入真实影像云时配置基础地址、有效X-Token及影像时区后重启后端；不要使用文档里的示例token。

URL在Langflow后端发起，容器中的`127.0.0.1`指向容器自身；上表适用于当前源码本机联调。模型超时或响应不明确仍转待人工确认，不自动重提。

04按完整文本匹配、忽略大小写；未命中仍保留待核实。医保耗材基础范围、目录映射、关联身份及时序等固定检查不因可配规则而失效。影像接口已按用户提供的文档映射；01/06等其他真实厂商接口仍待契约，未提供任意字段的可视化映射。

## Docker Compose运行

在仓库根目录执行。Python命令通过 `uv run`；先同步项目开发环境：

```bash
uv sync --frozen --package langflow-base --group dev --extra postgresql
uv run python scripts/verification/configure_demo.py
uv run python scripts/verification/build_flow.py
docker compose -f deploy/verification/compose.yaml build
docker compose -f deploy/verification/compose.yaml up -d postgres verification-init verification-api verification-demo langflow
```

`configure_demo.py` 新建权限0600的 `deploy/verification/.env`，不覆盖已存在文件、不打印密码；本次实施已生成此文件，再次运行可跳过该步骤。Compose默认从本仓库的 `docker/build_and_push.Dockerfile` 的base目标构建，包含当前改造源码；不能直接改用旧版 `latest` 镜像。首次完整构建依赖网络和前端编译。PostgreSQL固定17.10，Langflow源码版本1.12.0。

等待本地Langflow就绪后导入流程并创建Worker凭据：

如果私有`.env`中的 `VERIFICATION_LANGFLOW_API_KEY` 来自另一平台数据库（例如下方源码UI预览），先把该值置空，再执行导入；旧平台签发的key不能用于新部署。重新导入会写入该部署对应的flow_id。

```bash
uv run python scripts/verification/import_flow.py
docker compose -f deploy/verification/compose.yaml --profile worker up -d --force-recreate verification-api verification-worker
uv run python scripts/verification/submit_demo.py --reference demo-001
```

编排界面：`http://127.0.0.1:7860`，用户 `verification-admin`，密码读取私有 `.env` 的 `LANGFLOW_SUPERUSER_PASSWORD`。业务接口文档：`http://127.0.0.1:8080/docs`。端口默认仅绑定本机。`import_flow.py` 登录真实平台，导入已生成的JSON，保存平台生成的flow_id与API key；不把密钥写进流程。随后重新创建API/Worker以加载固定flow_id，再提交任务。重复导入按平台语义可能新建流程，正在执行时不切换流程。

预期结果：髋关节结算2套、模拟识别1套、单价10000，折算10000、差额-10000；膝关节结算与识别均为1套，结果一致。差额是按结算单价换算的比较值，不能直接认定基金损失。重复执行相同 `--reference` 查询同一任务，不重新识别；创建新任务使用新的监管编号。

停止服务：`docker compose -f deploy/verification/compose.yaml --profile worker stop`。数据库卷保留。不提供自动删库脚本。

## 从源码查看编排界面

本期没有修改React页面布局，也没有新增监管业务看板。可以查看“高值耗材核验(模拟联调)”流程，或从Verification分类拖出独立组件搭建新流程。本机原模拟画布的九个通用阶段已显式转换为对应独立类型，输入节点仍承载任务JSON，不表示调用聊天大模型。

以下步骤使用项目目录下的`deploy/verification/.cache/runtime`，已验证源码UI与模拟核验。原`/tmp/langflow-verification-venv`已失效，不再作为运行环境。当前根目录`.venv`仍未完成全仓依赖同步。

当前机器已恢复该环境；新机器或环境丢失时，可按下面命令重建专项运行环境（Python 3.13）：

```bash
cd /home/huangpan/github_repo/langflow
UV_CACHE_DIR=/tmp/langflow-uv-cache uv venv --python 3.13 deploy/verification/.cache/runtime
UV_CACHE_DIR=/tmp/langflow-uv-cache uv pip install --python deploy/verification/.cache/runtime/bin/python -r deploy/verification/requirements-source.txt
UV_CACHE_DIR=/tmp/langflow-uv-cache uv pip install --python deploy/verification/.cache/runtime/bin/python --no-deps -e src/lfx -e src/backend/base
```

`requirements-source.txt`记录本次恢复并验证的专项依赖，适用于源码UI和模拟核验，不替代根目录`uv.lock`的全功能依赖。服务进程退出后仍需重新启动；数据库和此环境均保存在项目目录或Docker卷中。


**终端一：启动源码后端。** 当前已有私有 `deploy/verification/.env`，不必再次生成。不要用shell的`source`加载这个文件，其中JSON配置应由dotenv读取。

```bash
cd /home/huangpan/github_repo/langflow
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python scripts/verification/run_local.py platform
```

此模式使用独立本地SQLite平台库，不需要启动业务PostgreSQL就能查看画布。源码中的核验模块通过可编辑安装加载；修改后端Python代码后重启该命令。

**终端二：安装并启动源码前端。** 本机Node 22与npm 10符合仓库要求。首次运行安装依赖，以后可跳过`npm ci`。

```bash
cd /home/huangpan/github_repo/langflow/src/frontend
PUPPETEER_SKIP_DOWNLOAD=true npm ci --cache /tmp/langflow-npm-cache --no-audit --no-fund
VITE_PROXY_TARGET=http://127.0.0.1:7860 npm run start -- --host 127.0.0.1 --port 3000 --strictPort
```

浏览器打开 <http://127.0.0.1:3000>。开发模式的页面在3000端口，API在7860端口；不需要先构建静态前端。登录用户名 `verification-admin`，密码是私有 `deploy/verification/.env` 中的 `LANGFLOW_SUPERUSER_PASSWORD`。

`PUPPETEER_SKIP_DOWNLOAD=true`只跳过测试工具附带的Chrome下载，不影响浏览器访问Vite页面；需要运行对应浏览器测试时另行安装测试浏览器。本次首次安装在Puppeteer写入用户缓存目录时失败，已在预览命令中明确跳过该无关下载。

**导入流程。** 登录后通过项目页上传 `deploy/verification/consumable-verification-palette.json`，再打开“高值耗材核验(模拟联调)”。也可以在第三个终端执行以下已提供脚本，它同时创建Worker的平台凭据并保存flow_id；同一平台只需导入一次。

```bash
cd /home/huangpan/github_repo/langflow
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python scripts/verification/import_flow.py
```

以上步骤只启动编排UI和平台API。实际核验还需要业务数据库、业务API、模拟上游、Worker，并给平台设置对应的`VERIFICATION_*_URL`。画布的00入口要求已受理任务的task_id/run_id/detail_ids，随意输入聊天文字不会执行完整任务；完整模拟运行参考Compose步骤或下方分进程配置。停止前后端分别在其终端按Ctrl+C，`.cache/source-ui`中的平台数据保留，该目录已被仓库忽略。

新机器或长期开发环境应先完成锁定依赖安装：

```bash
uv sync --frozen --package langflow-base --group dev --extra postgresql
```

安装成功后，把上面命令中的 `uv run --no-project --python deploy/verification/.cache/runtime/bin/python` 换成 `uv run --no-sync`，其余环境变量和参数不变。本次锁定依赖曾因下载失败未完成，所以快速步骤明确使用已验证的专项环境。

## 在当前源码实例执行完整模拟核验

本轮已启动完整模拟服务，演示记录见 [demo-walkthrough.md](demo-walkthrough.md)。本地前端3000、平台7860、核验API8080、模拟服务8090、PostgreSQL55432和一个Worker保持运行。本期没有新增任务看板；画布用于查看流程定义，提交脚本用于观察状态，业务API与导出JSON用于读取结果和证据。

当前机器可以直接再提交一项新任务：

```bash
cd /home/huangpan/github_repo/langflow
UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
  --python deploy/verification/.cache/runtime/bin/python \
  python scripts/verification/submit_demo.py \
  --reference walkthrough-20260928-002 \
  --output-dir deploy/verification/.cache/demo-runs
```

脚本使用私有配置里的模拟监管凭据，提交髋/膝两条明细，显示实际轮询到的状态变化，并按run_id保存`request.json`、`result.json`、`evidence.json`。轮询间隔1秒，不承诺捕获每个短暂阶段。结果包含`available=true`、`status=completed`、`stage=08`和结果版本时，表示结果已保存。失败或待人工确认会以非零退出码结束，不自动重跑。

相同`--reference`、相同内容复用已有任务及运行；想重新看一次完整调用链，改成新的编号。脚本将查询固定到受理时的run_id，避免之后发生人工重跑时混入另一轮结果。

### 全部停止后的恢复方法

业务库单独运行在Docker中，应用服务均使用当前源码。数据库镜像按已验证的17.10摘要固定，数据保存在`langflow-verification_postgres-data`卷中。

```bash
cd /home/huangpan/github_repo/langflow
docker compose -f deploy/verification/compose.yaml \
  -f deploy/verification/compose.source.yaml up -d --wait postgres
```

本机Docker配置引用了缺失的`docker-credential-desktop.exe`，直接拉取镜像会失败；本轮使用已缓存且验证为17.10的镜像，实际启动命令额外指定了`--pull never --no-build`。新机器需确保能拉取该镜像。

后续每个终端先进入仓库根目录，并定义这个快捷函数（长期锁定依赖安装完成后，可以改用项目的`uv run --no-sync python`）：

```bash
verification_python() {
  UV_CACHE_DIR=/tmp/langflow-uv-cache uv run --no-project \
    --python deploy/verification/.cache/runtime/bin/python python "$@"
}
```

数据库就绪后先执行一次：

```bash
verification_python scripts/verification/run_local.py init
```

再分别在四个终端运行以下常驻命令，不要同时启动第二个Worker：

```bash
# 终端一：替代上面的纯UI后端命令，继续使用相同平台SQLite库和账号
verification_python scripts/verification/run_local.py platform

# 终端二：核验业务API
verification_python scripts/verification/run_local.py api

# 终端三：模拟结算、影像云和识别服务
verification_python scripts/verification/run_local.py demo

# 终端四：仅一个Worker
verification_python scripts/verification/run_local.py worker
```

前端继续使用“从源码查看编排界面”中的Vite启动命令。已有预览库和流程时无需再次导入；全新平台在启动Worker前按前文运行导入脚本，导入后重启API以读取新flow_id。

本轮服务日志位于`deploy/verification/.cache/source-ui/`，可另开终端观察实际HTTP调用：

```bash
tail -f deploy/verification/.cache/source-ui/api.log \
  deploy/verification/.cache/source-ui/demo.log
```

`run_local.py`默认将日志输出到所在终端；上述文件是本轮启动时用shell重定向保存的。核验API文档为<http://127.0.0.1:8080/docs>，与Langflow自身的API文档不同；访问任务接口需使用私有配置里`VERIFICATION_CLIENTS`的对应Bearer token。不要在Langflow的Chat Input里直接填普通聊天文字或手动重复触发已经完成的run。

停止时分别在应用服务终端按Ctrl+C；数据库使用`docker compose -f deploy/verification/compose.yaml -f deploy/verification/compose.source.yaml stop postgres`，不删除数据卷。

## 不使用Compose的业务服务启动

设置环境变量后，API和Worker分别启动：

```bash
uv run python -m langflow.verification.database
uv run uvicorn langflow.verification.api:create_app --factory --host 127.0.0.1 --port 8080
uv run uvicorn langflow.verification.demo:create_demo_app --factory --host 127.0.0.1 --port 8090
uv run python -m langflow.verification.worker
```

每条常驻命令使用单独终端。Langflow使用项目现有启动方式，并设置 `LANGFLOW_COMPONENTS_PATH` 指向本目录的 `components`。业务API/Worker使用 `VerificationSettings`，画布仅需 `FlowSettings`，无需获得业务库密码或监管客户端密钥。业务库初始化命令只负责首版空库建表，不代替未来版本的迁移机制。

| 配置 | 用途 |
|---|---|
| `VERIFICATION_DATABASE_URL` | 业务数据库，生产形如`postgresql+psycopg://…`，与平台库隔离 |
| `VERIFICATION_DATABASE_SCHEMA` | 默认verification，业务账号拥有 |
| `VERIFICATION_CLIENTS` | JSON对象：来源系统→独立Bearer token |
| `VERIFICATION_INTERNAL_TOKEN` | 内部保存接口凭据，不能与客户端凭据相同 |
| `VERIFICATION_API_URL` | 流程访问核验API地址 |
| `VERIFICATION_LANGFLOW_URL` / `VERIFICATION_LANGFLOW_API_KEY` / `VERIFICATION_FLOW_ID` | Worker访问平台的固定配置 |
| `VERIFICATION_SETTLEMENT_URL` / `VERIFICATION_IMAGING_URL` / `VERIFICATION_MODEL_URL` | 三类上游契约服务根地址 |
| `VERIFICATION_UPSTREAM_TOKEN` | 上游契约服务凭据 |
| `VERIFICATION_DEMO_MODE` | 仅模拟联调为true，默认false |
| `VERIFICATION_CATALOG_MAPPING` | 已确认的目录代码→hip_prosthesis/knee_prosthesis |
| `VERIFICATION_RULE_VERSION` / `VERIFICATION_MONEY_TOLERANCE` / `VERIFICATION_CURRENCY` | 规则版本、金额容差和币种，领取前已固定到运行记录 |
| `VERIFICATION_REQUEST_TIMEOUT` / `VERIFICATION_FLOW_TIMEOUT` | 上游调用/整项HTTP等待上限，超时不重提 |

API/Worker与平台同机分进程即可。Compose创建不同数据库和非超级用户账号，撤销PUBLIC连接权限，业务schema只由业务账号拥有。只部署一个Worker；不对外承诺多Worker调度与自动恢复。

## 监管调用契约

全部业务路径前缀 `/api/v1/verification`。请求头：`Authorization: Bearer <对应来源token>`。

| 方法与路径 | 行为 |
|---|---|
| `POST /tasks` | 202，事务成功后返回task_id/run_id/状态；同号同内容复用，不同内容409 |
| `GET /tasks/by-reference/{external_task_id}` | 按当前来源和监管编号找回受理任务 |
| `GET /tasks/{task_id}?run_id=…` | 当前或指定历史运行状态 |
| `GET /tasks/{task_id}/runs?limit=50&offset=0` | 分页运行历史，最大200 |
| `GET /tasks/{task_id}/results?run_id=…&version=1` | 读取已保存结果，未生成时available=false，不触发执行 |
| `GET /tasks/{task_id}/evidence?run_id=…` | 快照、清单、请求输入及原始返回的关联证据 |
| `POST /tasks/{task_id}/runs/{run_id}/confirmation` | 人工确认中断/未知运行已结束，记录来源、原因和时间并关闭旧运行 |
| `POST /tasks/{task_id}/runs` | 人工确认后新建整项运行，保留固定任务范围和历史 |

提交最小形状：

```json
{
  "source_system": "demo-regulator",
  "external_task_id": "demo-001",
  "detail_ids": ["detail-hip", "detail-knee"],
  "config": {"days_before": 30, "days_after": 30, "reviewed_scopes": []}
}
```

没有人工核实的计数范围仍可获取识别原始结果，但相应种类/数量/费用返回未比较。完整可比较样本由 `demo.example_task()` 给出，其中 `reviewed_scopes` 明确明细组、检查组、类别、单位、目标/覆盖/计数确认和依据。一个明细不能分属两组；同一检查的同类识别总数不能分配给两组。侧别没有独立证据时不按单侧结果推断双侧数量。

人工操作请求体：

```json
{"confirmed_execution_ended": true, "reason": "已联系运行服务确认旧执行结束，重新核验"}
```

waiting/running/needs_confirmation不能直接重跑。running突退或未知运行先调用confirmation，确认者必须实际核实远端已停止。这个接口记录人工声明，不会终止远端进程。旧运行迟到写入会被拒绝；已存在结果的相同保存请求只返回原回执。

执行状态和比较结论分开：`completed`、`partial_failed`、`failed`、`needs_confirmation` 不等同于 `consistent`、`difference`、`not_compared`。每组结果给出所有 `detail_ids`；同价多明细合并比较一次，不复制识别总量到每行。`raw_recognition` 保留原值，`quantity`和`fee`保存用于比较的值。

## 上游v1归一化契约

这些路径是本次定义的适配契约，不宣称现有影像云或厂商已经提供。拿到真实协议后应在边界适配，并保留本契约和回归样本。

| 请求 | 返回 |
|---|---|
| `POST /v1/settlements/query`，`detail_ids` | `items: Settlement[]`，恰好包含每条固定明细，缺失/重复/越界失败 |
| `GET /v1/studies`，patient_id/hospital_id/encounter_id/modality/begin_time/end_time | `items: Study[]`，程序再次核对关联、时间及模态 |
| `GET /v1/studies/{study_id}/series` | `items: [{study_id, series_id}]` |
| `GET /v1/series/{series_id}/images` | `items: ImageRef[]`，保留study→series→UID→URL |
| `POST /v1/recognitions` | 本期选择同步200＋Recognition对象；异步202或无法解释的结果转待确认 |

详细字段在 `schemas.py`。`Settlement`使用归一化字段：`detail_id`是费用明细唯一键，`encounter_id`是就诊键；`settlement_time`对应SETL_TIME，`update_time`对应UPDATE_TIME；`quantity`/`unit_price`/`amount`对应CNT/PRIC/DET_ITEM_FEE_SUMAMT。费用数值使用十进制字符串，时间必须带时区。固定规则的金额精度0.01、单价输入最多6位小数、ROUND_HALF_UP及容差均留存；无已确认退费标识时不按正向费用比较。

模型POST前保存request_id及实际输入。模型服务负责DICOM下载、筛选、解码、预处理和已验证计数；返回处理/排除/失败UID清单、类别、原始数量、用于比较的数量、计数范围、单位、证据、版本和可选model_job_id。缺失、失败、不完整、无输入均不补0。逐图或逐序列数量不能直接用于检查级比较；排除项没有计数单元级验证时保守标记未比较。未提供模型版本时保存unknown。

## 测试

```bash
uv run pytest -c deploy/verification/pytest.ini deploy/verification/tests -q
uv run ruff check src/backend/base/langflow/verification deploy/verification scripts/verification
uv run ruff format --check src/backend/base/langflow/verification deploy/verification scripts/verification
```

测试使用独立pytest配置，避免启动与本业务无关的全平台测试夹具。`test_graph.py`会启动仅绑定127.0.0.1的临时API和模拟服务，将流程导出后重新载入真实Graph，逐节点执行再查询已保存结果。`test_postgres.py`需设置 `VERIFICATION_TEST_POSTGRES_URL`，为测试创建随机schema并只清理该schema；未配置时显式跳过。

本期不自动重提、恢复断点或复用旧运行模型结果。真实服务上线前还需外部契约、实际字段映射、独立病例、跨图去重计数依据和监管系统联调。
