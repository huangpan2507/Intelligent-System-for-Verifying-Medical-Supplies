"""Shared inputs and execution for the nine dedicated verification components."""

# ruff: noqa: RUF001 - Chinese UI labels intentionally use Chinese punctuation.

import json

import httpx
from lfx.custom.custom_component.component import Component
from lfx.io import DropdownInput, FloatInput, HandleInput, IntInput, MultiselectInput, Output, StrInput, TableInput
from lfx.schema.data import Data
from lfx.schema.message import Message


class VerificationStageComponent(Component):
    """Internal base; each palette component declares its fixed stage and inputs."""

    FIELD_LABELS = {
        "数量（quantity）": "quantity",
        "单价（unit_price）": "unit_price",
        "金额（amount）": "amount",
        "目录编码（catalog_code）": "catalog_code",
        "项目名称（item_name）": "item_name",
        "单位（unit）": "unit",
        "就诊类型（encounter_type）": "encounter_type",
        "医院编号（hospital_id）": "hospital_id",
        "医保支付（insurance_paid）": "insurance_paid",
        "耗材标志（medical_consumable）": "medical_consumable",
        "退费标志（is_reversal）": "is_reversal",
    }
    OPERATORS = {
        "等于": "eq",
        "不等于": "ne",
        "大于": "gt",
        "大于等于": "ge",
        "小于": "lt",
        "小于等于": "le",
        "包含文本": "contains",
        "属于列表": "in",
        "不属于列表": "not_in",
        "有值": "present",
        "缺失": "missing",
    }
    STAGE_FIELDS = {
        "02": ["filter_conditions", "filter_match", "filter_missing"],
        "03": ["studies_url", "days_before", "days_after", "modalities"],
        "04": ["body_field", "body_rules"],
        "05": ["series_url", "images_url"],
        "06": ["model_api_url"],
        "07": ["comparisons", "quantity_tolerance", "money_tolerance"],
    }
    STAGE_DESCRIPTIONS = {
        "00": "任务入口：核对已受理并领取的任务编号、运行编号和明细范围。输入由Worker提供。",
        "01": "接口查询：按任务明细编号获取结算数据并保存快照。接口地址和凭据由部署配置提供。",
        "02": "字段筛选：在医保耗材基础范围内，按字段、运算符和目标值组合附加条件。排除原因会保留。",
        "03": "检查关联：GET检查列表，取得study_primary_id；按患者、医院、就诊、时间窗及模态关联后传给部位初筛。",
        "04": "部位初筛：选择文本字段并维护类别词表，按完整文本匹配、忽略大小写；未命中保留待核实。",
        "05": "影像清单：用03/04传入的study_primary_id查询序列，再用series_id获取DICOM下载地址；保存清单。",
        "06": "模型识别：向配置的URL发送POST请求；先登记请求，保存原始响应。默认接入模拟服务。",
        "07": "结果比较：选择比较项目和绝对差容差。数量及费用仍须满足种类、计数范围、单位和证据条件。",
        "08": "结果保存：将比较结果和完成状态一起写入业务库，以保存回执确认成功。",
    }

    inputs = [
        HandleInput(
            name="context",
            display_name="核验上下文",
            input_types=["Data", "Message"],
            required=True,
            info="由上一步连线传入任务、数据和证据，无需手工填写。",
        ),
        TableInput(
            name="filter_conditions",
            display_name="附加筛选条件",
            show=False,
            input_types=[],
            trigger_text="配置筛选条件",
            trigger_icon="Filter",
            info="选择字段、运算符和目标值。列表用英文逗号分隔，布尔值用true/false。医保耗材和目录基础校验固定保留。",
            table_schema=[
                {
                    "name": "field",
                    "display_name": "筛选字段",
                    "formatter": "text",
                    "options": list(FIELD_LABELS),
                    "default": "数量（quantity）",
                },
                {
                    "name": "operator",
                    "display_name": "运算符",
                    "formatter": "text",
                    "options": list(OPERATORS),
                    "default": "大于等于",
                },
                {"name": "value", "display_name": "目标值", "formatter": "text", "edit_mode": "inline", "default": "0"},
            ],
            value=[{"field": "数量（quantity）", "operator": "大于等于", "value": "0"}],
        ),
        DropdownInput(
            name="filter_match",
            display_name="条件组合",
            options=["全部满足（AND）", "任一满足（OR）"],
            value="全部满足（AND）",
            show=False,
        ),
        DropdownInput(
            name="filter_missing",
            display_name="筛选字段缺值时",
            options=["保留待核实", "排除并记录原因"],
            value="保留待核实",
            show=False,
            info="缺值不当作0或空字符串参与比较。",
        ),
        StrInput(
            name="studies_url",
            display_name="检查列表 URL（GET）",
            value="",
            show=False,
            input_types=[],
            placeholder="http://127.0.0.1:8090/api/v2/study/list",
            info="影像云检查列表完整地址。患者、医院、就诊、时间窗及模态参数自动生成；留空使用部署默认地址。",
        ),
        IntInput(
            name="days_before",
            display_name="结算前查询天数",
            value=30,
            show=False,
            info="0—365天；画布配置优先于提交任务中的同名时间窗参数。",
        ),
        IntInput(name="days_after", display_name="结算后查询天数", value=30, show=False, info="0—365天。"),
        MultiselectInput(
            name="modalities", display_name="查询影像模态", options=["DR", "CT"], value=["DR", "CT"], show=False
        ),
        DropdownInput(
            name="body_field",
            display_name="部位判定字段",
            options=["部位（body_part）", "项目名称（project_name）"],
            value="部位（body_part）",
            show=False,
        ),
        TableInput(
            name="body_rules",
            display_name="部位类别词表",
            show=False,
            input_types=[],
            trigger_text="配置部位词表",
            info="完整文本匹配，忽略大小写。未命中保留待核实，不默认排除。",
            table_schema=[
                {
                    "name": "category",
                    "display_name": "所属类别",
                    "formatter": "text",
                    "options": ["髋关节", "膝关节", "明确无关"],
                    "default": "髋关节",
                },
                {"name": "term", "display_name": "匹配文本", "formatter": "text", "edit_mode": "inline", "default": ""},
            ],
            value=[
                {"category": category, "term": term}
                for category, terms in [
                    ("髋关节", ["hip", "髋关节", "髋"]),
                    ("膝关节", ["knee", "膝关节", "膝"]),
                    ("明确无关", ["chest", "head", "胸部", "头颅"]),
                ]
                for term in terms
            ],
        ),
        StrInput(
            name="series_url",
            display_name="序列查询 URL（GET）",
            value="",
            show=False,
            input_types=[],
            placeholder="http://127.0.0.1:8090/api/v2/dicom/series-instance-uid?study_primary_id={study_primary_id}",
            info="必须含{study_primary_id}，使用03返回且经04筛选的检查主键；留空使用部署默认序列接口。",
        ),
        StrInput(
            name="images_url",
            display_name="影像查询 URL（GET）",
            value="",
            show=False,
            input_types=[],
            placeholder="http://127.0.0.1:8090/api/v2/storage/dicom/sop-instance-uid?series_id={series_id}",
            info="必须含{series_id}；可追加url_type=0/1/2/3/4选择地址类型。留空使用部署默认影像接口。",
        ),
        StrInput(
            name="model_api_url",
            display_name="模型 API URL（POST）",
            value="",
            show=False,
            input_types=[],
            placeholder="http://127.0.0.1:8090/v1/recognitions",
            info="同步识别接口完整HTTP(S)地址。留空使用部署模型服务的/v1/recognitions；请求体由核验上下文生成。",
        ),
        MultiselectInput(
            name="comparisons",
            display_name="比较项目",
            options=["种类", "数量", "费用"],
            value=["种类", "数量", "费用"],
            show=False,
            info="至少选择一项。未选择的项目标记为未启用，不冒充一致。",
        ),
        FloatInput(
            name="quantity_tolerance",
            display_name="数量绝对差容差",
            value=0,
            show=False,
            info="绝对差不超过容差视为一致，原始差值仍保留。默认0，最大1000。",
        ),
        FloatInput(
            name="money_tolerance",
            display_name="金额绝对差容差（元）",
            value=0.01,
            show=False,
            info="0—1元，默认0.01；用于源金额校验和费用差比较。按结算单价折算，不代表基金损失。",
        ),
    ]
    outputs = [Output(name="verified_context", display_name="核验上下文", method="execute_stage")]

    def business_configuration(self):
        if self.stage == "02":
            return {
                "conditions": [
                    {
                        "field": self.FIELD_LABELS[row["field"]],
                        "operator": self.OPERATORS[row["operator"]],
                        "value": row.get("value", ""),
                    }
                    for row in self.filter_conditions
                ],
                "match": {"全部满足（AND）": "all", "任一满足（OR）": "any"}[self.filter_match],
                "missing": {"保留待核实": "needs_data", "排除并记录原因": "exclude"}[self.filter_missing],
            }
        if self.stage == "03":
            return {
                "studies_url": self.studies_url,
                "days_before": self.days_before,
                "days_after": self.days_after,
                "modalities": self.modalities,
            }
        if self.stage == "04":
            categories = {"髋关节": "hip_prosthesis", "膝关节": "knee_prosthesis", "明确无关": "unrelated"}
            return {
                "field": {"部位（body_part）": "body_part", "项目名称（project_name）": "project_name"}[
                    self.body_field
                ],
                "rules": [{"category": categories[row["category"]], "term": row["term"]} for row in self.body_rules],
            }
        if self.stage == "05":
            return {"series_url": self.series_url, "images_url": self.images_url}
        if self.stage == "06":
            return {"model_api_url": self.model_api_url}
        if self.stage == "07":
            fields = {"种类": "type", "数量": "quantity", "费用": "fee"}
            return {
                "comparisons": [fields[name] for name in self.comparisons],
                "quantity_tolerance": str(self.quantity_tolerance),
                "money_tolerance": str(self.money_tolerance),
            }
        return None

    async def execute_stage(self) -> Data:
        from langflow.verification.pipeline import Pipeline
        from langflow.verification.settings import FlowSettings

        if isinstance(self.context, Message):
            try:
                value = json.loads(self.context.text)
            except (json.JSONDecodeError, TypeError) as exc:
                msg = "任务输入须为已受理运行的JSON，包含task_id、run_id和detail_ids；请先通过核验API提交任务。"
                raise ValueError(msg) from exc
        else:
            value = self.context.data
        async with httpx.AsyncClient(follow_redirects=False) as http:
            context = await Pipeline(FlowSettings(), http).execute(self.stage, value, self.business_configuration())
        self.status = context.get("receipt", {"run_id": context["run_id"], "stage": self.stage})
        return Data(data=context)


def stage_inputs(stage: str) -> list:
    """Give each palette type its own inputs; fixed stages have no editable dispatcher."""
    names = {"context", *VerificationStageComponent.STAGE_FIELDS.get(stage, [])}
    return [
        field.model_copy(deep=True, update={"show": True})
        for field in VerificationStageComponent.inputs
        if field.name in names
    ]
