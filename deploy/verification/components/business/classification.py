# ruff: noqa: INP001 - discovered inline component bundle.
from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessClassification(BusinessComponent):
    display_name = "Business Classification"
    description = "Classify records with configurable rules, model fallback and input evidence."
    name = "BusinessClassification"
    kind = "classification"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
    ]
