from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessFilter(BusinessComponent):
    display_name = "Business Filter"
    description = "Persistent business datasets: filter"
    name = "BusinessFilter"
    kind = "filter"
    outputs = [
        Output(display_name="Matched", name="matched", method="out_matched", group_outputs=True),
        Output(display_name="Unmatched", name="unmatched", method="out_unmatched", group_outputs=True),
        Output(display_name="Unknown", name="unknown", method="out_unknown", group_outputs=True),
    ]
