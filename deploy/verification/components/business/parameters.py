from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessParameters(BusinessComponent):
    display_name = "Business Parameters"
    description = "Persistent business datasets: parameters"
    name = "BusinessParameters"
    kind = "parameters"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
