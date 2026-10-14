from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessModel(BusinessComponent):
    display_name = "Business Model"
    description = "Persistent business datasets: model"
    name = "BusinessModel"
    kind = "model"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
    ]
