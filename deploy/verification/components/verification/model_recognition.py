from langflow.verification.components import (
    VerificationStageComponent,
    stage_inputs,
)


class VerificationModelRecognition(VerificationStageComponent):
    display_name = "06 模型识别"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["06"]
    icon = "ScanEye"
    name = "VerificationModelRecognition"
    stage = "06"
    inputs = stage_inputs("06")
