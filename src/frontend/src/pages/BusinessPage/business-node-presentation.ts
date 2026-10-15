import { businessText } from "./business-i18n";

const defaults: Record<string, { name: string; description: string }> = {
  validate: {
    name: "Business Validate",
    description: "Persistent business datasets: validate",
  },
  transform: {
    name: "Business Transform",
    description: "Persistent business datasets: transform",
  },
  database: {
    name: "Business Database",
    description: "Persistent business datasets: database",
  },
  file: {
    name: "Business File",
    description: "Persistent business datasets: file",
  },
  databaselookup: {
    name: "Business Database Lookup",
    description:
      "Read related database records using upstream keys and validate the association.",
  },
  parameters: {
    name: "Business Parameters",
    description: "Persistent business datasets: parameters",
  },
  classification: {
    name: "Business Classification",
    description:
      "Classify records with configurable rules, model fallback and input evidence.",
  },
  api: {
    name: "Business Api",
    description: "Persistent business datasets: api",
  },
  taskinput: {
    name: "Business Task Start",
    description:
      "Start a regulatory task with accepted request parameters and task identifiers.",
  },
  join: {
    name: "Business Join",
    description: "Persistent business datasets: join",
  },
  model: {
    name: "Business Model",
    description: "Persistent business datasets: model",
  },
  output: {
    name: "Business Output",
    description: "Persistent business datasets: output",
  },
  filter: {
    name: "Business Filter",
    description: "Persistent business datasets: filter",
  },
  subflow: {
    name: "Business Subflow",
    description: "Persistent business datasets: subflow",
  },
  aggregate: {
    name: "Business Aggregate",
    description: "Persistent business datasets: aggregate",
  },
  union: {
    name: "Business Union",
    description: "Persistent business datasets: union",
  },
  imaging: {
    name: "Business Imaging",
    description: "Persistent business datasets: imaging",
  },
  compare: {
    name: "Business Compare",
    description: "Persistent business datasets: compare",
  },
};
const instances: Record<string, string> = {
  Request: "taskinput",
  "Task Start": "taskinput",
  Settlements: "database",
  SettlementChecks: "validate",
  Classification: "classification",
  Studies: "databaselookup",
  StudyRelevance: "classification",
  Series: "databaselookup",
  Images: "api",
  Observation: "imaging",
  Compare: "compare",
  Results: "output",
};

function kindOf(type?: string) {
  return type
    ?.split(":")
    .at(-1)
    ?.split("@")[0]
    ?.replace(/^Business/, "")
    .toLowerCase();
}

export function businessNodeName(type: string | undefined, name?: string) {
  const kind = kindOf(type);
  if (!kind || !defaults[kind] || !type?.includes("Business")) return name;
  if (name && instances[name] === kind)
    return businessText(`business.instance.${name}`);
  return name === defaults[kind].name
    ? businessText(`business.node.${kind}.name`)
    : name;
}

export function businessNodeDescription(
  type: string | undefined,
  description?: string,
) {
  const kind = kindOf(type);
  // Do not replace descriptions authored by users, or modify editable values.
  return kind &&
    type?.includes("Business") &&
    description === defaults[kind]?.description
    ? businessText(`business.node.${kind}.description`)
    : description;
}
