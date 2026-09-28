# 影像云三个HTTP接口的编排与映射

根据用户于2026-09-28提供的Apipost文档实现。文档地址用于查阅，接口URL中应填写影像云实际服务主机；当前本机仍使用模拟服务。未使用文档中的示例token或患者样例进行请求。

| 画布节点 | HTTP接口 | 输入/输出衔接 | 文档 |
|---|---|---|---|
| 03 检查关联 | GET `/api/v2/study/list` | 查询患者检查，取得`study_primary_id`，关联后交给04筛查 | [检查列表](https://docs.apipost.net/docs/detail/6dfae7d97c79000?locale=zh-cn&target_id=444ee13) |
| 05 影像清单 | GET `/api/v2/dicom/series-instance-uid` | Query：`study_primary_id`；返回`series_id` | [序列列表](https://docs.apipost.net/docs/detail/6dfae9144079000?target_id=1204a95cb12101&locale=zh-cn) |
| 05 影像清单 | GET `/api/v2/storage/dicom/sop-instance-uid` | Query：`series_id`，可选`url_type`；返回DICOM引用和地址 | [影像列表](https://docs.apipost.net/docs/detail/6dfaead25070000?target_id=11ffcb2c7120a1&locale=zh-cn) |

因此影像云共三个URL配置，03一个、05两个。03必须先获取检查资料，04才有项目/部位信息可筛查；05使用筛查后的检查主键继续调用。多个检查、序列按实际数量遍历，因此一个任务的HTTP请求次数可能多于三次。06另有模型POST接口。

## 字段对应

| 文档字段 | 核验内部字段/处理 |
|---|---|
| `study_primary_id` | 内部`study_id`的规范标识，同时显式保留`study_primary_id`；用于后续序列查询和人工核实范围 |
| `ris_study_id` | 单独保留，不能替代检查主键 |
| `organ_code` | `hospital_id`，须与结算侧医院统一社会信用代码对应 |
| `system_patient_id` | `patient_id`，须与结算侧患者编号对应 |
| `op_em_hp_ex_no` | `encounter_id` |
| `op_em_hp_ex_mark` | `1→outpatient`、`3→inpatient`；急诊/体检等未建立比较规则，保留待核实 |
| `chk_modality` | `modality`，仍限制已选DR/CT |
| `chk_dt` | `checked_at`；无时区字符串按`VERIFICATION_IMAGING_TIMEZONE`解析，默认Asia/Shanghai |
| `proj_name` / `ckpt_name` | 分别进入项目名称/部位筛查；完整原始行保存在`Study.raw`，不推断未知词条 |
| `series_id` | 传给第三个接口的序列主键；序列原始行与所属检查一并保存在影像清单工件 |
| `pacs_study_id` / `pacs_series_id` | 单独保留在序列原始数据中，不用作接口查询的主键 |
| `sop_instance_uid` | `image_uid`，用于影像去重和模型输入覆盖校验 |
| `study_instance_uid` / `series_instance_uid` | DICOM标识，保存在影像原始数据中，不冒充`study_primary_id`/`series_id` |
| `domain` + `file_path` | 生成下载URL，保留原有签名查询字符串；绝对HTTP(S)文件地址可直接使用，相对路径缺domain时报错 |

检查查询自动生成`begin_time/end_time`、`system_patient_id`、`organ_code`、`op_em_hp_ex_no`、`op_em_hp_ex_mark`和`chk_modality`。时间窗继续以结算时间为中心，并转换成影像云时区的`YYYY-MM-DD HH:mm:ss`。查询后再次核对患者、医院、就诊和住院/门诊时序；响应字段缺失不会用请求值补成已确认。

## 鉴权、结果与限制

三个接口均使用部署变量`VERIFICATION_IMAGING_TOKEN`作为`X-Token`。仅在模拟模式且未单独配置该变量时，使用本地生成的模拟上游token。真实模式不继承模型Bearer凭据。自定义URL只有与`VERIFICATION_IMAGING_URL`同协议、同主机、同端口时才携带部署影像凭据；不跟随重定向。

响应必须是HTTP成功、`code=200`、无非零`error.error_code`，且`data`为对象数组。HTTP200中的业务错误不能被当作空列表或成功。05检查序列的医院/模态与上游关联检查一致；第三个响应的所属检查/序列来自本次请求上下文，原始DICOM UID另存。相同SOP UID返回冲突引用时终止，不静默覆盖。

`url_type`可附加在影像URL中：0对象存储、1网关、2专网相对路径、3互联网、4专网。选择相对路径时仍须由响应提供可构成完整URL的domain；本期不猜测下载域名，也不在05下载DICOM。

真实接入仍需服务基础地址、有效X-Token、结算与影像的患者/医院/就诊编号对应关系，以及服务时区确认。当前模拟验证覆盖协议、鉴权、主键传递、下载URL生成和完整核验，不代表已经访问真实影像云或完成真实算法验收。
