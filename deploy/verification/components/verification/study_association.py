from langflow.verification.components import (
    ConsumableVerificationStage as VerificationStageComponent,
)
from langflow.verification.components import (
    stage_inputs,
)


class VerificationStudyAssociation(VerificationStageComponent):
    display_name = "03 检查关联"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["03"]
    icon = "Link"
    name = "VerificationStudyAssociation"
    stage = "03"
    inputs = stage_inputs("03")
