from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessImaging(BusinessComponent):
    display_name = "Business Imaging"
    description = "Persistent business datasets: imaging"
    name = "BusinessImaging"
    kind = "imaging"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
    ]
