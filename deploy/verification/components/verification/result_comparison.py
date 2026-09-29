from langflow.verification.components import (
    VerificationStageComponent,
    stage_inputs,
)


class VerificationResultComparison(VerificationStageComponent):
    display_name = "07 确定性比较"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["07"]
    icon = "Scale"
    name = "VerificationResultComparison"
    stage = "07"
    inputs = stage_inputs("07")
