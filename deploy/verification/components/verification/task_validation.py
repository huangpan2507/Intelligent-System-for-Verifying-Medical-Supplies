from langflow.verification.components import (
    VerificationStageComponent,
    stage_inputs,
)


class VerificationTaskValidation(VerificationStageComponent):
    display_name = "00 任务入口校验"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["00"]
    icon = "ClipboardCheck"
    name = "VerificationTaskValidation"
    stage = "00"
    inputs = stage_inputs("00")
