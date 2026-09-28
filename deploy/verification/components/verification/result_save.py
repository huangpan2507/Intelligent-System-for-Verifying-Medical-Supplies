from langflow.verification.components import (
    ConsumableVerificationStage as VerificationStageComponent,
)
from langflow.verification.components import (
    stage_inputs,
)


class VerificationResultSave(VerificationStageComponent):
    display_name = "08 结果保存"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["08"]
    icon = "Save"
    name = "VerificationResultSave"
    stage = "08"
    inputs = stage_inputs("08")
