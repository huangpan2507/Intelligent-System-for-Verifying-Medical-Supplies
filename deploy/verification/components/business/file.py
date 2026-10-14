from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessFile(BusinessComponent):
    display_name = "Business File"
    description = "Persistent business datasets: file"
    name = "BusinessFile"
    kind = "file"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
