from langflow.verification.components import (
    ConsumableVerificationStage as VerificationStageComponent,
)
from langflow.verification.components import (
    stage_inputs,
)


class VerificationBodyScreening(VerificationStageComponent):
    display_name = "04 部位初筛"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["04"]
    icon = "ScanSearch"
    name = "VerificationBodyScreening"
    stage = "04"
    inputs = stage_inputs("04")
