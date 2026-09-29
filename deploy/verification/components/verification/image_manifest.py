from langflow.verification.components import (
    VerificationStageComponent,
    stage_inputs,
)


class VerificationImageManifest(VerificationStageComponent):
    display_name = "05 影像清单"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["05"]
    icon = "Images"
    name = "VerificationImageManifest"
    stage = "05"
    inputs = stage_inputs("05")
