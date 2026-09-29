from langflow.verification.components import (
    VerificationStageComponent,
    stage_inputs,
)


class VerificationConsumableFilter(VerificationStageComponent):
    display_name = "02 耗材筛选"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["02"]
    icon = "Filter"
    name = "VerificationConsumableFilter"
    stage = "02"
    inputs = stage_inputs("02")
