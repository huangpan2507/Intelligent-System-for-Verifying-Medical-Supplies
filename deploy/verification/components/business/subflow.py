from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessSubflow(BusinessComponent):
    display_name = "Business Subflow"
    description = "Persistent business datasets: subflow"
    name = "BusinessSubflow"
    kind = "subflow"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
