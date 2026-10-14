from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessValidate(BusinessComponent):
    display_name = "Business Validate"
    description = "Persistent business datasets: validate"
    name = "BusinessValidate"
    kind = "validate"
    outputs = [
        Output(display_name="Valid", name="valid", method="out_valid", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
    ]
