from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessJoin(BusinessComponent):
    display_name = "Business Join"
    description = "Persistent business datasets: join"
    name = "BusinessJoin"
    kind = "join"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
    ]
