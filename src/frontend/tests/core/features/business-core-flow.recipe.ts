// Configuration recipe entered through UI controls; never posted as a graph.
export type Step = {
  name: string;
  kind: string;
  config: Record<string, any>;
  from?: string | string[];
  port?: string;
  contract?: Record<string, string>;
  reference?: string;
};
export const parameters = {
  hospital_name: "核心流程模拟医院",
  start: "2025-08-01 00:00:00",
  end: "2025-08-31 23:59:59",
};
const db = "537d8c03-3c9a-4c25-8a8e-d66cfc2b187a";
const api = "bd965b78-e1c6-4553-b884-c78a807b67bc";
const field = (name: string) => ({ field: name });
const param = (name: string) => ({ parameter: name });
const condition = (field: string, op: string, value: unknown) => ({
  field,
  op,
  value,
});
const against = (field: string, op: string, right_field: string) => ({
  field,
  op,
  right_field,
});
const copy = (field: string, output: string) => ({
  field,
  output,
  operation: "copy",
});
const expression = (expression: string, output: string) => ({
  expression,
  output,
  operation: "expression",
});
const identity = ["ORGAN_CODE", "DATA_SOURCE", "SETL_FEE_LIST_ID"];
const baseline = [
  "unit_row_id",
  ...identity,
  "ORGAN_NAME",
  "PSN_NO",
  "OP_EM_NO",
  "HILIST_NAME",
  "UPDATE_TIME",
  "CNT",
  "PRIC",
  "unit",
  "settled_amount",
];
const apiConfig = (
  path: string,
  body: Record<string, unknown>,
  context_fields: string[],
) => ({
  connection: api,
  path,
  method: "GET",
  body,
  items_path: "data",
  pagination: "none",
  max_calls: 10,
  context_fields,
  response_conditions: [
    { path: "code", equals: 200 },
    { path: "error.error_code", equals: 0 },
  ],
  completeness: {
    scope: "object",
    basis:
      "core-flow-v1 controlled mock returns the complete finite set for each request",
  },
});
export const steps: Step[] = [
  {
    name: "Request",
    kind: "parameters",
    config: {
      parameters: Object.entries(parameters).map(([name, value]) => ({
        name,
        type: "string",
        required: true,
        default: value,
      })),
    },
  },
  {
    name: "Settlements",
    kind: "database",
    from: "Request",
    config: {
      connection: db,
      schema: "public",
      table: "core_flow_settlement_v1",
      timezone: "Asia/Shanghai",
      conditions: [
        { field: "ORGAN_NAME", op: "eq", parameter: "hospital_name" },
        { field: "UPDATE_TIME", op: "ge", parameter: "start" },
        { field: "UPDATE_TIME", op: "le", parameter: "end" },
      ],
    },
  },
  {
    name: "SettlementChecks",
    kind: "validate",
    from: "Settlements",
    config: {
      required: [
        ...identity,
        "PSN_NO",
        "PSN_NAME",
        "CERTNO",
        "OP_EM_MARK",
        "OP_EM_NO",
        "UPDATE_TIME",
        "HILIST_NAME",
        "CNT",
        "PRIC",
      ],
      identity: {
        name: "settlement_detail",
        namespace: "core-flow-v1",
        keys: identity,
      },
      conditions: [condition("CNT", "ge", 0), condition("PRIC", "ge", 0)],
    },
  },
  {
    name: "NormalPaid",
    kind: "filter",
    from: "SettlementChecks",
    port: "valid",
    config: {
      logic: "and",
      conditions: [
        condition("MED_PAY_FLAG", "eq", "1"),
        condition("LIST_TYPE", "eq", "301"),
        condition("OP_EM_MARK", "eq", "3"),
        condition("REFD_SETL_FLAG", "eq", 0),
      ],
    },
  },
  {
    name: "TargetNames",
    kind: "filter",
    from: "NormalPaid",
    port: "matched",
    config: {
      logic: "or",
      conditions: [
        condition("HILIST_NAME", "contains", "人工髋关节"),
        condition("HILIST_NAME", "contains", "人工膝关节"),
      ],
    },
  },
  {
    name: "UnitContext",
    kind: "transform",
    from: "TargetNames",
    port: "matched",
    config: {
      transforms: [
        copy("_business_row_id", "unit_row_id"),
        expression("'套'", "unit"),
        expression("CNT * PRIC", "settled_amount"),
      ],
    },
  },
  {
    name: "Studies",
    kind: "api",
    from: "UnitContext",
    config: apiConfig(
      "/api/v2/study/list",
      {
        begin_time: param("start"),
        end_time: param("end"),
        name: field("PSN_NAME"),
        cardno: field("CERTNO"),
        organ_code: field("ORGAN_CODE"),
        op_em_hp_ex_mark: field("OP_EM_MARK"),
        op_em_hp_ex_no: field("OP_EM_NO"),
        chk_modality: "DR",
      },
      [
        "unit_row_id",
        "HILIST_NAME",
        "PSN_NAME",
        "ORGAN_CODE",
        "OP_EM_NO",
        "OP_EM_MARK",
        "UPDATE_TIME",
      ],
    ),
    reference:
      "https://docs.apipost.net/docs/detail/6dfae7d97c79000?locale=zh-cn&target_id=444ee13 — core-flow-v1 synthetic implementation",
    contract: {
      study_primary_id: "string",
      ris_study_id: "string",
      name: "string",
      system_patient_id: "string",
      organ_code: "string",
      op_em_hp_ex_mark: "string",
      op_em_hp_ex_no: "string",
      chk_modality: "string",
      is_upload: "integer",
      proj_name: "string",
      ckpt_name: "string",
      chk_dt: "string",
    },
  },
  {
    name: "CheckTimeText",
    kind: "transform",
    from: "Studies",
    config: {
      transforms: [
        expression("concat(chk_dt, '+08:00')", "chk_dt_zoned"),
        copy("_context_unit_row_id", "unit_row_id"),
      ],
    },
  },
  {
    name: "CheckTime",
    kind: "transform",
    from: "CheckTimeText",
    config: {
      transforms: [
        {
          field: "chk_dt_zoned",
          output: "checked_at",
          operation: "cast",
          type: "datetime",
        },
      ],
    },
  },
  {
    name: "StudyChecks",
    kind: "validate",
    from: "CheckTime",
    config: {
      required: [
        "study_primary_id",
        "name",
        "organ_code",
        "op_em_hp_ex_no",
        "chk_dt",
        "checked_at",
        "ckpt_name",
      ],
      conditions: [
        against("name", "eq", "_context_PSN_NAME"),
        against("organ_code", "eq", "_context_ORGAN_CODE"),
        against("op_em_hp_ex_no", "eq", "_context_OP_EM_NO"),
        against("op_em_hp_ex_mark", "eq", "_context_OP_EM_MARK"),
        condition("chk_modality", "eq", "DR"),
        condition("is_upload", "eq", 1),
        { field: "chk_dt", op: "ge", parameter: "start" },
        { field: "chk_dt", op: "le", parameter: "end" },
        against("checked_at", "lt", "_context_UPDATE_TIME"),
      ],
    },
  },
  ...["Hip", "Knee"].map((joint) => ({
    name: `${joint}Studies`,
    kind: "filter",
    from: "StudyChecks",
    port: "valid",
    config: {
      logic: "and",
      conditions: [
        condition(
          "_context_HILIST_NAME",
          "contains",
          joint === "Hip" ? "人工髋关节" : "人工膝关节",
        ),
        condition(
          "ckpt_name",
          "contains",
          joint === "Hip" ? "髋关节" : "膝关节",
        ),
      ],
    },
  })),
  {
    name: "JointStudies",
    kind: "union",
    from: ["HipStudies", "KneeStudies"],
    port: "matched",
    config: {},
  },
  {
    name: "Series",
    kind: "api",
    from: "JointStudies",
    config: apiConfig(
      "/api/v2/dicom/series-instance-uid",
      { study_primary_id: field("study_primary_id") },
      ["unit_row_id", "organ_code"],
    ),
    reference:
      "https://docs.apipost.net/docs/detail/6dfae9144079000?target_id=1204a95cb12101&locale=zh-cn — core-flow-v1 synthetic implementation",
    contract: {
      series_id: "string",
      organ_code: "string",
      chk_modality: "string",
    },
  },
  {
    name: "SeriesChecks",
    kind: "validate",
    from: "Series",
    config: {
      required: ["series_id"],
      conditions: [
        against("organ_code", "eq", "_context_organ_code"),
        condition("chk_modality", "eq", "DR"),
      ],
    },
  },
  {
    name: "SeriesContext",
    kind: "transform",
    from: "SeriesChecks",
    port: "valid",
    config: {
      transforms: [copy("_context_unit_row_id", "unit_row_id")],
    },
  },
  {
    name: "Images",
    kind: "api",
    from: "SeriesContext",
    config: apiConfig(
      "/api/v2/storage/dicom/sop-instance-uid",
      { series_id: field("series_id"), url_type: "3" },
      ["unit_row_id"],
    ),
    reference:
      "https://docs.apipost.net/docs/detail/6dfaead25070000?target_id=11ffcb2c7120a1&locale=zh-cn — core-flow-v1 synthetic implementation",
    contract: {
      domain: "string",
      file_path: "string",
      study_instance_uid: "string",
      series_instance_uid: "string",
      sop_instance_uid: "string",
    },
  },
  {
    name: "ImageContext",
    kind: "transform",
    from: "Images",
    config: {
      transforms: [
        copy("_context_unit_row_id", "unit_row_id"),
        expression("concat(domain, file_path)", "file_ref"),
      ],
    },
  },
  {
    name: "ImageChecks",
    kind: "validate",
    from: "ImageContext",
    config: {
      required: [
        "domain",
        "file_path",
        "file_ref",
        "study_instance_uid",
        "series_instance_uid",
        "sop_instance_uid",
      ],
      identity: {
        name: "unit_image",
        namespace: "core-flow-images-v1",
        keys: ["unit_row_id", "sop_instance_uid"],
      },
    },
  },
  {
    name: "Manifests",
    kind: "aggregate",
    from: "ImageChecks",
    port: "valid",
    config: {
      group_by: ["unit_row_id"],
      metrics: [
        { field: "file_ref", operation: "collect", output: "image_manifest" },
      ],
    },
  },
  {
    name: "UnitEvidence",
    kind: "join",
    from: ["UnitContext", "Manifests"],
    config: {
      keys: [{ left: "unit_row_id", right: "unit_row_id" }],
      how: "left",
      cardinality: "one_to_one",
    },
  },
  {
    name: "ObservationInput",
    kind: "transform",
    from: "UnitEvidence",
    config: {
      transforms: [
        ...baseline.map((name) => copy(`left_${name}`, name)),
        copy("right_image_manifest", "image_manifest"),
      ],
    },
  },
  {
    name: "EvidenceChecks",
    kind: "validate",
    from: "ObservationInput",
    config: { required: ["image_manifest"] },
  },
  {
    name: "Observation",
    kind: "imaging",
    from: "EvidenceChecks",
    port: "valid",
    config: {
      connection: api,
      path: "/business/core-flow/imaging",
      patient_field: "PSN_NO",
      hospital_field: "ORGAN_CODE",
      encounter_field: "OP_EM_NO",
      category_field: "HILIST_NAME",
      unit_field: "unit",
      evidence_field: "image_manifest",
      max_calls: 10,
    },
  },
  {
    name: "ObservationChecks",
    kind: "validate",
    from: "Observation",
    config: {
      required: ["recognized_category", "recognized_quantity", "evidence_ref"],
      conditions: [
        condition("recognition_confirmed", "eq", true),
        condition("coverage_confirmed", "eq", true),
        condition("recognized_quantity", "ge", 0),
        against("observed_unit", "eq", "unit"),
      ],
    },
  },
  ...["Hip", "Knee"].map((joint) => ({
    name: `${joint}Category`,
    kind: "filter",
    from: "ObservationChecks",
    port: "valid",
    config: {
      logic: "and",
      conditions: [
        condition(
          "HILIST_NAME",
          "contains",
          joint === "Hip" ? "人工髋关节" : "人工膝关节",
        ),
        condition(
          "recognized_category",
          "eq",
          joint === "Hip" ? "人工髋关节" : "人工膝关节",
        ),
      ],
    },
  })),
  {
    name: "EqualCategories",
    kind: "union",
    from: ["HipCategory", "KneeCategory"],
    port: "matched",
    config: {},
  },
  {
    name: "Amounts",
    kind: "transform",
    from: "EqualCategories",
    config: {
      transforms: [
        expression("'equal'", "category_status"),
        expression("recognized_quantity * PRIC", "observed_amount"),
      ],
    },
  },
  {
    name: "CompareQuantityFee",
    kind: "compare",
    from: "Amounts",
    config: {
      comparisons: [
        {
          left: "CNT",
          right: "recognized_quantity",
          mode: "numeric",
          tolerance: 0,
        },
        {
          left: "settled_amount",
          right: "observed_amount",
          mode: "numeric",
          tolerance: 0,
        },
      ],
    },
  },
  {
    name: "ResultFields",
    kind: "transform",
    from: "CompareQuantityFee",
    config: {
      transforms: [
        copy("comparison_0", "quantity_status"),
        copy("comparison_1", "amount_status"),
      ],
    },
  },
  {
    name: "Results",
    kind: "output",
    from: "ResultFields",
    config: {
      name: "核心流程核验结果",
      primary: true,
      columns: [
        ...baseline,
        "recognized_category",
        "recognized_quantity",
        "observed_amount",
        "category_status",
        "quantity_status",
        "amount_status",
        "difference_0",
        "difference_1",
        "evidence_ref",
        "image_manifest",
        "simulated",
      ],
      obligation: {
        mode: "verification",
        sources: [{ node: "@Settlements", identity: "@SettlementChecks" }],
        checks: [
          ["category", "category_status"],
          ["quantity", "quantity_status"],
          ["fee", "amount_status"],
        ].map(([name, status_field]) => ({
          name,
          units: { node: "@UnitContext", port: "data" },
          results: [
            {
              node: "@ResultFields",
              port: "data",
              status_field,
              evidence_field: "evidence_ref",
            },
          ],
        })),
      },
    },
  },
];
