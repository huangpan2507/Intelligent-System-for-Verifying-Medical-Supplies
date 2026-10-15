import { useTranslation } from "./business-i18n";

const operators: Record<string, string> = {
  eq: "=",
  ne: "≠",
  gt: ">",
  ge: "≥",
  lt: "<",
  le: "≤",
  in: "IN",
};

export default function DatabaseConditionHelp({
  value,
  regulatoryTask,
}: {
  value: unknown;
  regulatoryTask?: boolean;
}) {
  const { t } = useTranslation();
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const condition = value as Record<string, unknown>;
  const { field, op, parameter } = condition;
  if (typeof field !== "string" || !field || typeof op !== "string")
    return null;
  const operator = operators[op];
  if (!operator) return null;

  let description: string;
  if (typeof parameter === "string" && parameter) {
    if (
      regulatoryTask &&
      field === "ORGAN_NAME" &&
      op === "eq" &&
      parameter === "hospital_name"
    ) {
      description = t("business.database.conditionHelp.hospital", { field });
    } else if (
      regulatoryTask &&
      field === "UPDATE_TIME" &&
      op === "ge" &&
      parameter === "start"
    ) {
      description = t("business.database.conditionHelp.start", { field });
    } else if (
      regulatoryTask &&
      field === "UPDATE_TIME" &&
      op === "le" &&
      parameter === "end"
    ) {
      description = t("business.database.conditionHelp.end", { field });
    } else {
      description = t("business.database.conditionHelp.parameter", {
        field,
        operator,
        parameter,
      });
    }
  } else if ("parameter" in condition || condition.value === undefined) {
    return null;
  } else {
    description = t("business.database.conditionHelp.constant", {
      field,
      operator,
      value: JSON.stringify(condition.value),
    });
  }

  return (
    <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
      {description}
    </p>
  );
}
