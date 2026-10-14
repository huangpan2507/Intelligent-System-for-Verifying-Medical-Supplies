from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessApi(BusinessComponent):
    display_name = "Business Api"
    description = "Persistent business datasets: api"
    name = "BusinessApi"
    kind = "api"
    outputs = [
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
