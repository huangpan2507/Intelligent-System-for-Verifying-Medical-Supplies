# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core/features/business-compact-core.spec.ts >> compact core canvas exposes reusable nodes and correctly scoped lookup fields
- Location: tests/core/features/business-compact-core.spec.ts:5:5

# Error details

```
Error: expect(locator).toHaveValue(expected) failed

Locator: getByTestId('business-canvas-configuration').getByText('Settlement-side calculated amount = CNT * PRIC', { exact: true }).locator('..').getByRole('textbox', { name: 'Expression', exact: true })
Expected: "CNT * PRIC + 0"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toHaveValue" with timeout 5000ms
  - waiting for getByTestId('business-canvas-configuration').getByText('Settlement-side calculated amount = CNT * PRIC', { exact: true }).locator('..').getByRole('textbox', { name: 'Expression', exact: true })

```

```yaml
- banner:
  - button "Go to home"
  - button "Starter Project"
  - text: /
  - button "Edit flow details and settings for 髋膝关节正常核心流程（数据库＋API，精简11节点）"
  - button "Tasks And Results"
  - button "Schemes"
  - button "Go to GitHub repo"
  - button "Go to Discord server"
  - button "Notifications and errors"
  - button "User":
    - img "User"
- navigation "Components sidebar":
  - list:
    - listitem:
      - button "Components"
    - listitem:
      - button "MCP"
    - listitem:
      - button "Bundles"
    - listitem:
      - button "Versions"
    - listitem:
      - button "Agent"
    - listitem:
      - button "Memories"
    - listitem:
      - button "Traces"
  - searchbox "Components"
  - img /
  - text: Components
  - button "Component settings"
  - list:
    - listitem:
      - button "Business"
    - listitem:
      - button "Input & Output"
    - listitem:
      - button "Data Sources"
    - listitem:
      - button "Models & Agents"
    - listitem:
      - button "LLM Operations"
    - listitem:
      - button "Files & Knowledge"
    - listitem:
      - button "Processing"
    - listitem:
      - button "Flow Control"
    - listitem:
      - button "Verification"
  - button "Discover more components"
  - button "New Custom Component"
- main:
  - button "Langflow Assistant":
    - img "Langflow Assistant"
  - button "Zoom canvas control, 65%": 65%
  - button "Add Sticky Note"
  - button "Minimize all"
  - button "Help"
  - button "Playground" [disabled]
  - button "Share"
  - application "Flow canvas":
    - button "Edge from Compare to Results"
    - button "Edge from Images to Observation"
    - button "Edge from Observation to Compare"
    - button "Edge from Classification to Studies"
    - button "Edge from SettlementChecks to Classification"
    - button "Edge from Series to Images"
    - button "Edge from StudyRelevance to Series"
    - button "Edge from Studies to StudyRelevance"
    - button "Edge from Task Start to Settlements"
    - button "Edge from Settlements to SettlementChecks"
    - application "Task Start node":
      - text: Task Start
      - button "Run component"
      - paragraph: Start a regulatory task with accepted request parameters and task identifiers.
      - text: Task input
      - button "Please build the component first" [disabled]
      - button "Output handle for Task input on node Task Start"
    - application "Settlements node":
      - text: Settlements
      - button "Run component"
      - paragraph: "Persistent business datasets: database"
      - button "Input handle for Parameters on node Settlements"
      - text: Parameters Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Settlements"
    - application "SettlementChecks node":
      - text: SettlementChecks
      - button "Run component"
      - paragraph: "Persistent business datasets: validate"
      - button "Input handle for Data on node SettlementChecks"
      - text: Data required Valid
      - button "Please build the component first" [disabled]
      - button "Output handle for Valid on node SettlementChecks"
      - text: Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node SettlementChecks"
    - application "Classification node":
      - text: Classification
      - button "Run component"
      - paragraph: Classify records with configurable rules, model fallback and input evidence.
      - button "Input handle for Data on node Classification"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Classification"
      - text: Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node Classification"
    - application "Studies node":
      - text: Studies
      - button "Run component"
      - paragraph: Read related database records using upstream keys and validate the association.
      - button "Input handle for Data on node Studies"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Studies"
      - text: Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node Studies"
    - application "StudyRelevance node":
      - text: StudyRelevance
      - button "Run component"
      - paragraph: Classify records with configurable rules, model fallback and input evidence.
      - button "Input handle for Data on node StudyRelevance"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node StudyRelevance"
      - text: Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node StudyRelevance"
    - application "Series node":
      - text: Series
      - button "Run component"
      - paragraph: Read related database records using upstream keys and validate the association.
      - button "Input handle for Data on node Series"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Series"
      - text: Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node Series"
    - application "Images node":
      - text: Images
      - button "Run component"
      - paragraph: "Persistent business datasets: api"
      - button "Input handle for Data on node Images"
      - text: Data Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node Images"
      - text: Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Images"
    - application "Observation node":
      - text: Observation
      - button "Run component"
      - paragraph: "Persistent business datasets: imaging"
      - button "Input handle for Data on node Observation"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Observation"
      - text: Issues
      - button "Please build the component first" [disabled]
      - button "Output handle for Issues on node Observation"
    - application "Compare node":
      - button "Code"
      - button "Parameters"
      - button "Freeze"
      - combobox "Show More"
      - button "Edit node details"
      - text: Compare
      - button "Run component"
      - paragraph: "Persistent business datasets: compare"
      - button "Input handle for Data on node Compare"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Compare"
    - application "Results node":
      - text: Results
      - button "Run component"
      - paragraph: "Persistent business datasets: output"
      - button "Input handle for Data on node Results"
      - text: Data required Data
      - button "Please build the component first" [disabled]
      - button "Output handle for Data on node Results"
  - strong: Business configuration
  - button "Narrow Editor"
  - button "Collapse"
  - paragraph: Configuration is saved in this canvas. Field choices come from upstream nodes; resolve schema errors before publication.
  - paragraph: Compare
  - group:
    - text: Data to use
    - paragraph: "Upstream dataset: Observation"
  - group:
    - text: Calculate before comparing
    - paragraph: Settlement-side calculated amount = CNT * PRIC + 0 · Recognition-side calculated amount = recognized_quantity * PRIC
    - paragraph: Calculations run in list order before comparisons. Converted amounts are calculated from quantity and price, not returned by recognition.
    - group:
      - text: Settlement-side calculated amount = CNT * PRIC + 0 Operation *
      - combobox "Operation":
        - option "Choose"
        - option "Copy"
        - option "Cast"
        - option "Map"
        - option "Expression" [selected]
      - text: Output *
      - textbox "Output": settled_amount
      - text: Expression *
      - textbox "Expression": CNT * PRIC + 0
      - button "Remove"
    - group: Recognition-side calculated amount = recognized_quantity * PRIC
    - button "Add Calculation"
    - group: Traceability details
  - group:
    - text: What to compare
    - paragraph: Settlement category ↔ Recognized category · Exact equality · Settlement quantity ↔ Recognized quantity · Numeric equality · Settlement-side calculated amount ↔ Recognition-side calculated amount · Numeric equality
    - paragraph: Numeric comparisons require equality, without tolerance or automatic rounding. 1, 1.0 and 1.00 are equal. Null settings apply to missing values; blockers remain effective.
    - paragraph: Category comparison
    - text: Left
    - combobox "Left":
      - option "Choose"
      - option "Observation._identity · VARCHAR"
      - option "Observation.ORGAN_CODE · VARCHAR"
      - option "Observation.ORGAN_NAME · VARCHAR"
      - option "Observation.ORGAN_ADMDVS · VARCHAR"
      - option "Observation.ORGAN_LV · VARCHAR"
      - option "Observation.FIX_ORGAN_CODE · VARCHAR"
      - option "Observation.FIX_ORGAN_NAME · VARCHAR"
      - option "Observation.DATA_SOURCE · VARCHAR"
      - option "Observation.SETL_HOS_ID · VARCHAR"
      - option "Observation.INIT_SETL_HOS_ID · VARCHAR"
      - option "Observation.SETL_MED_ID · VARCHAR"
      - option "Observation.INIT_SETL_MED_ID · VARCHAR"
      - option "Observation.MDTRT_SN · VARCHAR"
      - option "Observation.MDTRT_ID · VARCHAR"
      - option "Observation.MED_PAY_FLAG · VARCHAR"
      - option "Observation.PSN_NO · VARCHAR"
      - option "Observation.PSN_NAME · VARCHAR"
      - option "Observation.PSN_CERT_TYPE · VARCHAR"
      - option "Observation.CERTNO · VARCHAR"
      - option "Observation.SOC_SEC_CARD_NO · VARCHAR"
      - option "Observation.GEND · VARCHAR"
      - option "Observation.OP_EM_MARK · VARCHAR"
      - option "Observation.OP_EM_NO · VARCHAR"
      - option "Observation.RCD_DT · VARCHAR"
      - option "Observation.REFD_SETL_FLAG · DECIMAL(1,0)"
      - option "Observation.MED_TYPE · VARCHAR"
      - option "Observation.MEDFEE_SUMAMT · DECIMAL(16,2)"
      - option "Observation.FUND_PAY_SUMAMT · DECIMAL(16,2)"
      - option "Observation.PSN_PART_AMT · DECIMAL(16,2)"
      - option "Observation.ACCT_PAY · DECIMAL(16,2)"
      - option "Observation.PSN_CASH_PAY · DECIMAL(16,2)"
      - option "Observation.HOSP_PART_AMT · DECIMAL(16,2)"
      - option "Observation.UPDATE_TIME · TIMESTAMP WITH TIME ZONE"
      - option "Observation.SETL_FEE_LIST_ID · VARCHAR"
      - option "Observation.RPT_NO · VARCHAR"
      - option "Observation.FEEDETL_SN · VARCHAR"
      - option "Observation.INIT_FEEDETL_SN · VARCHAR"
      - option "Observation.HOS_PROJ_NO · VARCHAR"
      - option "Observation.HOS_PROJ_NAME · VARCHAR"
      - option "Observation.HILIST_CODE · VARCHAR"
      - option "Observation.HILIST_NAME · VARCHAR"
      - option "Observation.LIST_TYPE · VARCHAR"
      - option "Observation.MED_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_NAME · VARCHAR"
      - option "Observation.MED_CHRGITM_TYPE · VARCHAR"
      - option "Observation.PRODNAME · VARCHAR"
      - option "Observation.SPEC · VARCHAR"
      - option "Observation.DOSFORM_NAME · VARCHAR"
      - option "Observation.CNT · DECIMAL(10,2)"
      - option "Observation.PRIC · DECIMAL(10,2)"
      - option "Observation.SYSTEM_ID · VARCHAR"
      - option "Observation.target_category · VARCHAR" [selected]
      - option "Observation.classification_method · VARCHAR"
      - option "Observation.classification_reason · VARCHAR"
      - option "Observation.classification_evidence_field · VARCHAR"
      - option "Observation.classification_evidence_text · VARCHAR"
      - option "Observation.classification_confidence · DECIMAL(38,6)"
      - option "Observation._representative_row_id · BIGINT"
      - option "Observation.image_manifest_context · JSON"
      - option "Observation.image_manifest · JSON"
      - option "Observation.recognized_category · text"
      - option "Observation.recognized_quantity · number"
      - option "Observation.observed_unit · text"
      - option "Observation.coverage_confirmed · boolean"
      - option "Observation.evidence_ref · text"
      - option "Observation.recognition_confirmed · boolean"
      - option "Observation.simulated · boolean"
      - option "Observation._issue_reason · text"
      - option "Observation._model_response · text"
      - option "Observation._request_id · text"
      - option "Observation._business_row_id · BIGINT"
      - option "unit_row_id · BIGINT"
      - option "settled_amount · DECIMAL(18,4)"
      - option "observed_amount · DECIMAL(38,8)"
    - text: Mode
    - combobox "Mode":
      - option "Exact equality" [selected]
      - option "Numeric equality"
      - option "Case-insensitive equality"
    - text: Right
    - combobox "Right":
      - option "Choose"
      - option "Observation._identity · VARCHAR"
      - option "Observation.ORGAN_CODE · VARCHAR"
      - option "Observation.ORGAN_NAME · VARCHAR"
      - option "Observation.ORGAN_ADMDVS · VARCHAR"
      - option "Observation.ORGAN_LV · VARCHAR"
      - option "Observation.FIX_ORGAN_CODE · VARCHAR"
      - option "Observation.FIX_ORGAN_NAME · VARCHAR"
      - option "Observation.DATA_SOURCE · VARCHAR"
      - option "Observation.SETL_HOS_ID · VARCHAR"
      - option "Observation.INIT_SETL_HOS_ID · VARCHAR"
      - option "Observation.SETL_MED_ID · VARCHAR"
      - option "Observation.INIT_SETL_MED_ID · VARCHAR"
      - option "Observation.MDTRT_SN · VARCHAR"
      - option "Observation.MDTRT_ID · VARCHAR"
      - option "Observation.MED_PAY_FLAG · VARCHAR"
      - option "Observation.PSN_NO · VARCHAR"
      - option "Observation.PSN_NAME · VARCHAR"
      - option "Observation.PSN_CERT_TYPE · VARCHAR"
      - option "Observation.CERTNO · VARCHAR"
      - option "Observation.SOC_SEC_CARD_NO · VARCHAR"
      - option "Observation.GEND · VARCHAR"
      - option "Observation.OP_EM_MARK · VARCHAR"
      - option "Observation.OP_EM_NO · VARCHAR"
      - option "Observation.RCD_DT · VARCHAR"
      - option "Observation.REFD_SETL_FLAG · DECIMAL(1,0)"
      - option "Observation.MED_TYPE · VARCHAR"
      - option "Observation.MEDFEE_SUMAMT · DECIMAL(16,2)"
      - option "Observation.FUND_PAY_SUMAMT · DECIMAL(16,2)"
      - option "Observation.PSN_PART_AMT · DECIMAL(16,2)"
      - option "Observation.ACCT_PAY · DECIMAL(16,2)"
      - option "Observation.PSN_CASH_PAY · DECIMAL(16,2)"
      - option "Observation.HOSP_PART_AMT · DECIMAL(16,2)"
      - option "Observation.UPDATE_TIME · TIMESTAMP WITH TIME ZONE"
      - option "Observation.SETL_FEE_LIST_ID · VARCHAR"
      - option "Observation.RPT_NO · VARCHAR"
      - option "Observation.FEEDETL_SN · VARCHAR"
      - option "Observation.INIT_FEEDETL_SN · VARCHAR"
      - option "Observation.HOS_PROJ_NO · VARCHAR"
      - option "Observation.HOS_PROJ_NAME · VARCHAR"
      - option "Observation.HILIST_CODE · VARCHAR"
      - option "Observation.HILIST_NAME · VARCHAR"
      - option "Observation.LIST_TYPE · VARCHAR"
      - option "Observation.MED_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_NAME · VARCHAR"
      - option "Observation.MED_CHRGITM_TYPE · VARCHAR"
      - option "Observation.PRODNAME · VARCHAR"
      - option "Observation.SPEC · VARCHAR"
      - option "Observation.DOSFORM_NAME · VARCHAR"
      - option "Observation.CNT · DECIMAL(10,2)"
      - option "Observation.PRIC · DECIMAL(10,2)"
      - option "Observation.SYSTEM_ID · VARCHAR"
      - option "Observation.target_category · VARCHAR"
      - option "Observation.classification_method · VARCHAR"
      - option "Observation.classification_reason · VARCHAR"
      - option "Observation.classification_evidence_field · VARCHAR"
      - option "Observation.classification_evidence_text · VARCHAR"
      - option "Observation.classification_confidence · DECIMAL(38,6)"
      - option "Observation._representative_row_id · BIGINT"
      - option "Observation.image_manifest_context · JSON"
      - option "Observation.image_manifest · JSON"
      - option "Observation.recognized_category · text" [selected]
      - option "Observation.recognized_quantity · number"
      - option "Observation.observed_unit · text"
      - option "Observation.coverage_confirmed · boolean"
      - option "Observation.evidence_ref · text"
      - option "Observation.recognition_confirmed · boolean"
      - option "Observation.simulated · boolean"
      - option "Observation._issue_reason · text"
      - option "Observation._model_response · text"
      - option "Observation._request_id · text"
      - option "Observation._business_row_id · BIGINT"
      - option "unit_row_id · BIGINT"
      - option "settled_amount · DECIMAL(18,4)"
      - option "observed_amount · DECIMAL(38,8)"
    - group: Result field and null settings
    - button "Remove"
    - paragraph: Quantity comparison
    - text: Left
    - combobox "Left":
      - option "Choose"
      - option "Observation._identity · VARCHAR"
      - option "Observation.ORGAN_CODE · VARCHAR"
      - option "Observation.ORGAN_NAME · VARCHAR"
      - option "Observation.ORGAN_ADMDVS · VARCHAR"
      - option "Observation.ORGAN_LV · VARCHAR"
      - option "Observation.FIX_ORGAN_CODE · VARCHAR"
      - option "Observation.FIX_ORGAN_NAME · VARCHAR"
      - option "Observation.DATA_SOURCE · VARCHAR"
      - option "Observation.SETL_HOS_ID · VARCHAR"
      - option "Observation.INIT_SETL_HOS_ID · VARCHAR"
      - option "Observation.SETL_MED_ID · VARCHAR"
      - option "Observation.INIT_SETL_MED_ID · VARCHAR"
      - option "Observation.MDTRT_SN · VARCHAR"
      - option "Observation.MDTRT_ID · VARCHAR"
      - option "Observation.MED_PAY_FLAG · VARCHAR"
      - option "Observation.PSN_NO · VARCHAR"
      - option "Observation.PSN_NAME · VARCHAR"
      - option "Observation.PSN_CERT_TYPE · VARCHAR"
      - option "Observation.CERTNO · VARCHAR"
      - option "Observation.SOC_SEC_CARD_NO · VARCHAR"
      - option "Observation.GEND · VARCHAR"
      - option "Observation.OP_EM_MARK · VARCHAR"
      - option "Observation.OP_EM_NO · VARCHAR"
      - option "Observation.RCD_DT · VARCHAR"
      - option "Observation.REFD_SETL_FLAG · DECIMAL(1,0)"
      - option "Observation.MED_TYPE · VARCHAR"
      - option "Observation.MEDFEE_SUMAMT · DECIMAL(16,2)"
      - option "Observation.FUND_PAY_SUMAMT · DECIMAL(16,2)"
      - option "Observation.PSN_PART_AMT · DECIMAL(16,2)"
      - option "Observation.ACCT_PAY · DECIMAL(16,2)"
      - option "Observation.PSN_CASH_PAY · DECIMAL(16,2)"
      - option "Observation.HOSP_PART_AMT · DECIMAL(16,2)"
      - option "Observation.UPDATE_TIME · TIMESTAMP WITH TIME ZONE"
      - option "Observation.SETL_FEE_LIST_ID · VARCHAR"
      - option "Observation.RPT_NO · VARCHAR"
      - option "Observation.FEEDETL_SN · VARCHAR"
      - option "Observation.INIT_FEEDETL_SN · VARCHAR"
      - option "Observation.HOS_PROJ_NO · VARCHAR"
      - option "Observation.HOS_PROJ_NAME · VARCHAR"
      - option "Observation.HILIST_CODE · VARCHAR"
      - option "Observation.HILIST_NAME · VARCHAR"
      - option "Observation.LIST_TYPE · VARCHAR"
      - option "Observation.MED_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_NAME · VARCHAR"
      - option "Observation.MED_CHRGITM_TYPE · VARCHAR"
      - option "Observation.PRODNAME · VARCHAR"
      - option "Observation.SPEC · VARCHAR"
      - option "Observation.DOSFORM_NAME · VARCHAR"
      - option "Observation.CNT · DECIMAL(10,2)" [selected]
      - option "Observation.PRIC · DECIMAL(10,2)"
      - option "Observation.SYSTEM_ID · VARCHAR"
      - option "Observation.target_category · VARCHAR"
      - option "Observation.classification_method · VARCHAR"
      - option "Observation.classification_reason · VARCHAR"
      - option "Observation.classification_evidence_field · VARCHAR"
      - option "Observation.classification_evidence_text · VARCHAR"
      - option "Observation.classification_confidence · DECIMAL(38,6)"
      - option "Observation._representative_row_id · BIGINT"
      - option "Observation.image_manifest_context · JSON"
      - option "Observation.image_manifest · JSON"
      - option "Observation.recognized_category · text"
      - option "Observation.recognized_quantity · number"
      - option "Observation.observed_unit · text"
      - option "Observation.coverage_confirmed · boolean"
      - option "Observation.evidence_ref · text"
      - option "Observation.recognition_confirmed · boolean"
      - option "Observation.simulated · boolean"
      - option "Observation._issue_reason · text"
      - option "Observation._model_response · text"
      - option "Observation._request_id · text"
      - option "Observation._business_row_id · BIGINT"
      - option "unit_row_id · BIGINT"
      - option "settled_amount · DECIMAL(18,4)"
      - option "observed_amount · DECIMAL(38,8)"
    - text: Mode
    - combobox "Mode":
      - option "Exact equality"
      - option "Numeric equality" [selected]
      - option "Case-insensitive equality"
    - text: Right
    - combobox "Right":
      - option "Choose"
      - option "Observation._identity · VARCHAR"
      - option "Observation.ORGAN_CODE · VARCHAR"
      - option "Observation.ORGAN_NAME · VARCHAR"
      - option "Observation.ORGAN_ADMDVS · VARCHAR"
      - option "Observation.ORGAN_LV · VARCHAR"
      - option "Observation.FIX_ORGAN_CODE · VARCHAR"
      - option "Observation.FIX_ORGAN_NAME · VARCHAR"
      - option "Observation.DATA_SOURCE · VARCHAR"
      - option "Observation.SETL_HOS_ID · VARCHAR"
      - option "Observation.INIT_SETL_HOS_ID · VARCHAR"
      - option "Observation.SETL_MED_ID · VARCHAR"
      - option "Observation.INIT_SETL_MED_ID · VARCHAR"
      - option "Observation.MDTRT_SN · VARCHAR"
      - option "Observation.MDTRT_ID · VARCHAR"
      - option "Observation.MED_PAY_FLAG · VARCHAR"
      - option "Observation.PSN_NO · VARCHAR"
      - option "Observation.PSN_NAME · VARCHAR"
      - option "Observation.PSN_CERT_TYPE · VARCHAR"
      - option "Observation.CERTNO · VARCHAR"
      - option "Observation.SOC_SEC_CARD_NO · VARCHAR"
      - option "Observation.GEND · VARCHAR"
      - option "Observation.OP_EM_MARK · VARCHAR"
      - option "Observation.OP_EM_NO · VARCHAR"
      - option "Observation.RCD_DT · VARCHAR"
      - option "Observation.REFD_SETL_FLAG · DECIMAL(1,0)"
      - option "Observation.MED_TYPE · VARCHAR"
      - option "Observation.MEDFEE_SUMAMT · DECIMAL(16,2)"
      - option "Observation.FUND_PAY_SUMAMT · DECIMAL(16,2)"
      - option "Observation.PSN_PART_AMT · DECIMAL(16,2)"
      - option "Observation.ACCT_PAY · DECIMAL(16,2)"
      - option "Observation.PSN_CASH_PAY · DECIMAL(16,2)"
      - option "Observation.HOSP_PART_AMT · DECIMAL(16,2)"
      - option "Observation.UPDATE_TIME · TIMESTAMP WITH TIME ZONE"
      - option "Observation.SETL_FEE_LIST_ID · VARCHAR"
      - option "Observation.RPT_NO · VARCHAR"
      - option "Observation.FEEDETL_SN · VARCHAR"
      - option "Observation.INIT_FEEDETL_SN · VARCHAR"
      - option "Observation.HOS_PROJ_NO · VARCHAR"
      - option "Observation.HOS_PROJ_NAME · VARCHAR"
      - option "Observation.HILIST_CODE · VARCHAR"
      - option "Observation.HILIST_NAME · VARCHAR"
      - option "Observation.LIST_TYPE · VARCHAR"
      - option "Observation.MED_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_NAME · VARCHAR"
      - option "Observation.MED_CHRGITM_TYPE · VARCHAR"
      - option "Observation.PRODNAME · VARCHAR"
      - option "Observation.SPEC · VARCHAR"
      - option "Observation.DOSFORM_NAME · VARCHAR"
      - option "Observation.CNT · DECIMAL(10,2)"
      - option "Observation.PRIC · DECIMAL(10,2)"
      - option "Observation.SYSTEM_ID · VARCHAR"
      - option "Observation.target_category · VARCHAR"
      - option "Observation.classification_method · VARCHAR"
      - option "Observation.classification_reason · VARCHAR"
      - option "Observation.classification_evidence_field · VARCHAR"
      - option "Observation.classification_evidence_text · VARCHAR"
      - option "Observation.classification_confidence · DECIMAL(38,6)"
      - option "Observation._representative_row_id · BIGINT"
      - option "Observation.image_manifest_context · JSON"
      - option "Observation.image_manifest · JSON"
      - option "Observation.recognized_category · text"
      - option "Observation.recognized_quantity · number" [selected]
      - option "Observation.observed_unit · text"
      - option "Observation.coverage_confirmed · boolean"
      - option "Observation.evidence_ref · text"
      - option "Observation.recognition_confirmed · boolean"
      - option "Observation.simulated · boolean"
      - option "Observation._issue_reason · text"
      - option "Observation._model_response · text"
      - option "Observation._request_id · text"
      - option "Observation._business_row_id · BIGINT"
      - option "unit_row_id · BIGINT"
      - option "settled_amount · DECIMAL(18,4)"
      - option "observed_amount · DECIMAL(38,8)"
    - group: Result field and null settings
    - button "Remove"
    - paragraph: Amount comparison
    - text: Left
    - combobox "Left":
      - option "Choose"
      - option "Observation._identity · VARCHAR"
      - option "Observation.ORGAN_CODE · VARCHAR"
      - option "Observation.ORGAN_NAME · VARCHAR"
      - option "Observation.ORGAN_ADMDVS · VARCHAR"
      - option "Observation.ORGAN_LV · VARCHAR"
      - option "Observation.FIX_ORGAN_CODE · VARCHAR"
      - option "Observation.FIX_ORGAN_NAME · VARCHAR"
      - option "Observation.DATA_SOURCE · VARCHAR"
      - option "Observation.SETL_HOS_ID · VARCHAR"
      - option "Observation.INIT_SETL_HOS_ID · VARCHAR"
      - option "Observation.SETL_MED_ID · VARCHAR"
      - option "Observation.INIT_SETL_MED_ID · VARCHAR"
      - option "Observation.MDTRT_SN · VARCHAR"
      - option "Observation.MDTRT_ID · VARCHAR"
      - option "Observation.MED_PAY_FLAG · VARCHAR"
      - option "Observation.PSN_NO · VARCHAR"
      - option "Observation.PSN_NAME · VARCHAR"
      - option "Observation.PSN_CERT_TYPE · VARCHAR"
      - option "Observation.CERTNO · VARCHAR"
      - option "Observation.SOC_SEC_CARD_NO · VARCHAR"
      - option "Observation.GEND · VARCHAR"
      - option "Observation.OP_EM_MARK · VARCHAR"
      - option "Observation.OP_EM_NO · VARCHAR"
      - option "Observation.RCD_DT · VARCHAR"
      - option "Observation.REFD_SETL_FLAG · DECIMAL(1,0)"
      - option "Observation.MED_TYPE · VARCHAR"
      - option "Observation.MEDFEE_SUMAMT · DECIMAL(16,2)"
      - option "Observation.FUND_PAY_SUMAMT · DECIMAL(16,2)"
      - option "Observation.PSN_PART_AMT · DECIMAL(16,2)"
      - option "Observation.ACCT_PAY · DECIMAL(16,2)"
      - option "Observation.PSN_CASH_PAY · DECIMAL(16,2)"
      - option "Observation.HOSP_PART_AMT · DECIMAL(16,2)"
      - option "Observation.UPDATE_TIME · TIMESTAMP WITH TIME ZONE"
      - option "Observation.SETL_FEE_LIST_ID · VARCHAR"
      - option "Observation.RPT_NO · VARCHAR"
      - option "Observation.FEEDETL_SN · VARCHAR"
      - option "Observation.INIT_FEEDETL_SN · VARCHAR"
      - option "Observation.HOS_PROJ_NO · VARCHAR"
      - option "Observation.HOS_PROJ_NAME · VARCHAR"
      - option "Observation.HILIST_CODE · VARCHAR"
      - option "Observation.HILIST_NAME · VARCHAR"
      - option "Observation.LIST_TYPE · VARCHAR"
      - option "Observation.MED_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_NAME · VARCHAR"
      - option "Observation.MED_CHRGITM_TYPE · VARCHAR"
      - option "Observation.PRODNAME · VARCHAR"
      - option "Observation.SPEC · VARCHAR"
      - option "Observation.DOSFORM_NAME · VARCHAR"
      - option "Observation.CNT · DECIMAL(10,2)"
      - option "Observation.PRIC · DECIMAL(10,2)"
      - option "Observation.SYSTEM_ID · VARCHAR"
      - option "Observation.target_category · VARCHAR"
      - option "Observation.classification_method · VARCHAR"
      - option "Observation.classification_reason · VARCHAR"
      - option "Observation.classification_evidence_field · VARCHAR"
      - option "Observation.classification_evidence_text · VARCHAR"
      - option "Observation.classification_confidence · DECIMAL(38,6)"
      - option "Observation._representative_row_id · BIGINT"
      - option "Observation.image_manifest_context · JSON"
      - option "Observation.image_manifest · JSON"
      - option "Observation.recognized_category · text"
      - option "Observation.recognized_quantity · number"
      - option "Observation.observed_unit · text"
      - option "Observation.coverage_confirmed · boolean"
      - option "Observation.evidence_ref · text"
      - option "Observation.recognition_confirmed · boolean"
      - option "Observation.simulated · boolean"
      - option "Observation._issue_reason · text"
      - option "Observation._model_response · text"
      - option "Observation._request_id · text"
      - option "Observation._business_row_id · BIGINT"
      - option "unit_row_id · BIGINT"
      - option "settled_amount · DECIMAL(18,4)" [selected]
      - option "observed_amount · DECIMAL(38,8)"
    - text: Mode
    - combobox "Mode":
      - option "Exact equality"
      - option "Numeric equality" [selected]
      - option "Case-insensitive equality"
    - text: Right
    - combobox "Right":
      - option "Choose"
      - option "Observation._identity · VARCHAR"
      - option "Observation.ORGAN_CODE · VARCHAR"
      - option "Observation.ORGAN_NAME · VARCHAR"
      - option "Observation.ORGAN_ADMDVS · VARCHAR"
      - option "Observation.ORGAN_LV · VARCHAR"
      - option "Observation.FIX_ORGAN_CODE · VARCHAR"
      - option "Observation.FIX_ORGAN_NAME · VARCHAR"
      - option "Observation.DATA_SOURCE · VARCHAR"
      - option "Observation.SETL_HOS_ID · VARCHAR"
      - option "Observation.INIT_SETL_HOS_ID · VARCHAR"
      - option "Observation.SETL_MED_ID · VARCHAR"
      - option "Observation.INIT_SETL_MED_ID · VARCHAR"
      - option "Observation.MDTRT_SN · VARCHAR"
      - option "Observation.MDTRT_ID · VARCHAR"
      - option "Observation.MED_PAY_FLAG · VARCHAR"
      - option "Observation.PSN_NO · VARCHAR"
      - option "Observation.PSN_NAME · VARCHAR"
      - option "Observation.PSN_CERT_TYPE · VARCHAR"
      - option "Observation.CERTNO · VARCHAR"
      - option "Observation.SOC_SEC_CARD_NO · VARCHAR"
      - option "Observation.GEND · VARCHAR"
      - option "Observation.OP_EM_MARK · VARCHAR"
      - option "Observation.OP_EM_NO · VARCHAR"
      - option "Observation.RCD_DT · VARCHAR"
      - option "Observation.REFD_SETL_FLAG · DECIMAL(1,0)"
      - option "Observation.MED_TYPE · VARCHAR"
      - option "Observation.MEDFEE_SUMAMT · DECIMAL(16,2)"
      - option "Observation.FUND_PAY_SUMAMT · DECIMAL(16,2)"
      - option "Observation.PSN_PART_AMT · DECIMAL(16,2)"
      - option "Observation.ACCT_PAY · DECIMAL(16,2)"
      - option "Observation.PSN_CASH_PAY · DECIMAL(16,2)"
      - option "Observation.HOSP_PART_AMT · DECIMAL(16,2)"
      - option "Observation.UPDATE_TIME · TIMESTAMP WITH TIME ZONE"
      - option "Observation.SETL_FEE_LIST_ID · VARCHAR"
      - option "Observation.RPT_NO · VARCHAR"
      - option "Observation.FEEDETL_SN · VARCHAR"
      - option "Observation.INIT_FEEDETL_SN · VARCHAR"
      - option "Observation.HOS_PROJ_NO · VARCHAR"
      - option "Observation.HOS_PROJ_NAME · VARCHAR"
      - option "Observation.HILIST_CODE · VARCHAR"
      - option "Observation.HILIST_NAME · VARCHAR"
      - option "Observation.LIST_TYPE · VARCHAR"
      - option "Observation.MED_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_CODG · VARCHAR"
      - option "Observation.MEDINS_LIST_NAME · VARCHAR"
      - option "Observation.MED_CHRGITM_TYPE · VARCHAR"
      - option "Observation.PRODNAME · VARCHAR"
      - option "Observation.SPEC · VARCHAR"
      - option "Observation.DOSFORM_NAME · VARCHAR"
      - option "Observation.CNT · DECIMAL(10,2)"
      - option "Observation.PRIC · DECIMAL(10,2)"
      - option "Observation.SYSTEM_ID · VARCHAR"
      - option "Observation.target_category · VARCHAR"
      - option "Observation.classification_method · VARCHAR"
      - option "Observation.classification_reason · VARCHAR"
      - option "Observation.classification_evidence_field · VARCHAR"
      - option "Observation.classification_evidence_text · VARCHAR"
      - option "Observation.classification_confidence · DECIMAL(38,6)"
      - option "Observation._representative_row_id · BIGINT"
      - option "Observation.image_manifest_context · JSON"
      - option "Observation.image_manifest · JSON"
      - option "Observation.recognized_category · text"
      - option "Observation.recognized_quantity · number"
      - option "Observation.observed_unit · text"
      - option "Observation.coverage_confirmed · boolean"
      - option "Observation.evidence_ref · text"
      - option "Observation.recognition_confirmed · boolean"
      - option "Observation.simulated · boolean"
      - option "Observation._issue_reason · text"
      - option "Observation._model_response · text"
      - option "Observation._request_id · text"
      - option "Observation._business_row_id · BIGINT"
      - option "unit_row_id · BIGINT"
      - option "settled_amount · DECIMAL(18,4)"
      - option "observed_amount · DECIMAL(38,8)" [selected]
    - group: Result field and null settings
    - button "Remove"
    - button "Add Comparison"
  - group:
    - text: Output and acceptance
    - paragraph: Data retains equal, different or unknown results; differences are right minus left.
- region "Notifications":
  - status
```

# Test source

```ts
  330 |       .getByText("Addresses, item identifiers and per-item context", {
  331 |         exact: true,
  332 |       })
  333 |       .click();
  334 |     await expect(collection).toContainText("RPT_NO");
  335 |     await expect(
  336 |       collection.getByRole("textbox", { name: "Output", exact: true }),
  337 |     ).toHaveValue("image_manifest");
  338 |     await page.screenshot({
  339 |       path: test.info().outputPath("images-wide.png"),
  340 |       fullPage: true,
  341 |     });
  342 |     await panel.getByRole("button", { name: /Narrow Editor/i }).click();
  343 |     await page.screenshot({
  344 |       path: test.info().outputPath("images-narrow.png"),
  345 |       fullPage: true,
  346 |     });
  347 |     await selectNode("Observation");
  348 |     for (const group of [
  349 |       "service",
  350 |       "evidence",
  351 |       "scope",
  352 |       "validity",
  353 |       "output",
  354 |     ]) {
  355 |       await expect(
  356 |         panel.getByTestId(`configuration-section-imaging-${group}`),
  357 |       ).toBeVisible();
  358 |     }
  359 |     for (const key of ["quantity_field", "unit_field", "unit_value"]) {
  360 |       await expect(panel.getByTestId(`business-field-${key}`)).toHaveCount(0);
  361 |     }
  362 |     const scope = panel.getByTestId("configuration-section-imaging-scope");
  363 |     await expect(scope).toContainText("ORGAN_CODE");
  364 |     await expect(scope).toContainText("PSN_NO");
  365 |     await expect(scope).toContainText("OP_EM_NO");
  366 |     await scope.locator(":scope > summary").click();
  367 |     await scope.getByText("Edit field bindings", { exact: true }).click();
  368 |     await expect(
  369 |       scope.getByRole("combobox", { name: "Patient field", exact: true }),
  370 |     ).toHaveValue("PSN_NO");
  371 |     await expect(panel.getByRole("alert")).toHaveCount(0);
  372 |     await expect
  373 |       .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
  374 |       .toBe(true);
  375 |     await page.screenshot({
  376 |       path: test.info().outputPath("observation-narrow.png"),
  377 |       fullPage: true,
  378 |     });
  379 |     await panel.getByRole("button", { name: /Widen Editor/i }).click();
  380 |     await expect(panel).toHaveClass(/w-\[56rem\]/);
  381 |     await page.screenshot({
  382 |       path: test.info().outputPath("observation-wide.png"),
  383 |       fullPage: true,
  384 |     });
  385 |     await panel.getByRole("button", { name: /Narrow Editor/i }).click();
  386 |     await selectNode("Compare");
  387 |     await expect(
  388 |       panel.locator('[data-testid^="configuration-section-compare-"]'),
  389 |     ).toHaveCount(4);
  390 |     expect(
  391 |       await panel
  392 |         .locator('[data-testid^="configuration-section-compare-"]')
  393 |         .evaluateAll((elements) =>
  394 |           elements.map((el) => el.getAttribute("data-testid")),
  395 |         ),
  396 |     ).toEqual([
  397 |       "configuration-section-compare-source",
  398 |       "configuration-section-compare-calculations",
  399 |       "configuration-section-compare-comparisons",
  400 |       "configuration-section-compare-output",
  401 |     ]);
  402 |     await expect(panel.getByTestId("business-field-tolerance")).toHaveCount(0);
  403 |     await expect(panel.getByRole("alert")).toHaveCount(0);
  404 |     await expect(
  405 |       panel.getByTestId("configuration-section-compare-calculations"),
  406 |     ).toContainText("CNT * PRIC");
  407 |     await expect(
  408 |       panel.getByTestId("configuration-section-compare-comparisons"),
  409 |     ).toContainText("Numeric equality");
  410 |     await expect
  411 |       .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
  412 |       .toBe(true);
  413 |     await page.screenshot({
  414 |       path: test.info().outputPath("compare-narrow.png"),
  415 |       fullPage: true,
  416 |     });
  417 |     await panel.getByRole("button", { name: /Widen Editor/i }).click();
  418 |     await expect(panel).toHaveClass(/w-\[56rem\]/);
  419 |     const calculation = panel
  420 |       .getByText("Settlement-side calculated amount = CNT * PRIC", {
  421 |         exact: true,
  422 |       })
  423 |       .locator("..");
  424 |     await calculation.locator(":scope > summary").click();
  425 |     const expression = calculation.getByRole("textbox", {
  426 |       name: "Expression",
  427 |       exact: true,
  428 |     });
  429 |     await expression.fill("CNT * PRIC + 0");
> 430 |     await expect(expression).toHaveValue("CNT * PRIC + 0");
      |                              ^ Error: expect(locator).toHaveValue(expected) failed
  431 |     await expression.fill("CNT * PRIC");
  432 |     await expect(
  433 |       calculation.getByRole("combobox", { name: "Field", exact: true }),
  434 |     ).toHaveCount(0);
  435 |     await page.screenshot({
  436 |       path: test.info().outputPath("compare-wide.png"),
  437 |       fullPage: true,
  438 |     });
  439 |     await panel.getByRole("button", { name: /Narrow Editor/i }).click();
  440 |     await page.keyboard.press("Control+s");
  441 |     await page.reload({ waitUntil: "domcontentloaded" });
  442 |     await expect(panel).toBeVisible({ timeout: 60_000 });
  443 |     await selectNode("Compare");
  444 |     await expect(
  445 |       panel.getByTestId("configuration-section-compare-calculations"),
  446 |     ).toContainText("CNT * PRIC");
  447 |     await expect(
  448 |       panel.getByTestId("configuration-section-compare-calculations"),
  449 |     ).not.toContainText("CNT * PRIC + 0");
  450 |     await selectNode("SettlementChecks");
  451 |     await panel
  452 |       .getByText("System-managed identity details (read-only)", { exact: true })
  453 |       .click();
  454 |     await expect(
  455 |       panel.getByText("core-flow-v1", { exact: true }),
  456 |     ).toBeVisible();
  457 |     await page.evaluate(() =>
  458 |       localStorage.setItem("languagePreference", "zh-Hans"),
  459 |     );
  460 |     await page.reload({ waitUntil: "domcontentloaded" });
  461 |     await expect(panel).toBeVisible({ timeout: 60_000 });
  462 |     await page.getByTestId("canvas_controls_dropdown").click();
  463 |     await page.getByTestId("fit_view").click();
  464 |     await page.keyboard.press("Escape");
  465 |     await panel.getByRole("button", { name: "收起", exact: true }).click();
  466 |     await page.getByTestId("rf__node-Classification").click();
  467 |     await panel.getByRole("button", { name: "展开", exact: true }).click();
  468 |     await expect(
  469 |       panel.getByTestId("configuration-section-classification-rules"),
  470 |     ).toContainText("判断规则与复核");
  471 |     await expect(panel).toContainText("上游数据集：SettlementChecks", {
  472 |       timeout: 60_000,
  473 |     });
  474 |     await expect
  475 |       .poll(() =>
  476 |         panel.evaluate(
  477 |           (element) => element.scrollWidth <= element.clientWidth + 1,
  478 |         ),
  479 |       )
  480 |       .toBe(true);
  481 |     await page.screenshot({
  482 |       path: test.info().outputPath("classification-zh-narrow.png"),
  483 |       fullPage: true,
  484 |     });
  485 |     await panel.getByRole("button", { name: "收起", exact: true }).click();
  486 |     await page.getByTestId("rf__node-Observation").click();
  487 |     await panel.getByRole("button", { name: "展开", exact: true }).click();
  488 |     await expect(
  489 |       panel.getByTestId("configuration-section-imaging-service"),
  490 |     ).toContainText("识别服务");
  491 |     await expect(
  492 |       panel.getByTestId("configuration-section-imaging-scope"),
  493 |     ).toContainText("影像属于谁");
  494 |     await expect(
  495 |       panel.getByTestId("configuration-section-imaging-validity"),
  496 |     ).toContainText("不做件／套换算");
  497 |     await expect(
  498 |       panel
  499 |         .getByTestId("configuration-section-imaging-validity")
  500 |         .locator(":scope > summary"),
  501 |     ).toContainText("识别数量 ≥ 0");
  502 |     await expect(panel.getByRole("alert")).toHaveCount(0);
  503 |     await expect
  504 |       .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
  505 |       .toBe(true);
  506 |     await page.screenshot({
  507 |       path: test.info().outputPath("observation-zh-narrow.png"),
  508 |       fullPage: true,
  509 |     });
  510 |     await panel.getByRole("button", { name: "收起", exact: true }).click();
  511 |     await page.getByTestId("rf__node-Compare").click();
  512 |     await panel.getByRole("button", { name: "展开", exact: true }).click();
  513 |     await expect(
  514 |       panel.getByTestId("configuration-section-compare-calculations"),
  515 |     ).toContainText("比较前计算");
  516 |     await expect(
  517 |       panel.getByTestId("configuration-section-compare-comparisons"),
  518 |     ).toContainText("数值相等");
  519 |     await expect(panel.getByRole("alert")).toHaveCount(0);
  520 |     await expect
  521 |       .poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1))
  522 |       .toBe(true);
  523 |     await page.screenshot({
  524 |       path: test.info().outputPath("compare-zh-narrow.png"),
  525 |       fullPage: true,
  526 |     });
  527 |     await page.evaluate(() => localStorage.setItem("languagePreference", "en"));
  528 |     await page.reload({ waitUntil: "domcontentloaded" });
  529 |     await page.goto(`/business/tasks/${report.task_id}`, {
  530 |       waitUntil: "domcontentloaded",
```