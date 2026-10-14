import type en from "@/locales/en.json";
export const getModalPropsApiKey = (
  t: (key: Extract<keyof typeof en, `modal.secretKey.${string}`>) => string,
) => {
  const modalProps = {
    title: t("modal.secretKey.createTitle"),
    description: t("modal.secretKey.createDescription"),
    inputPlaceholder: t("modal.secretKey.inputPlaceholder"),
    buttonText: t("modal.secretKey.generateButton"),
    generatedKeyMessage: (
      <>
        {" "}
        {t("modal.secretKey.generatedKeyPart1")}{" "}
        <strong>{t("modal.secretKey.generatedKeyBold")}</strong>{" "}
        {t("modal.secretKey.generatedKeyPart2")}
      </>
    ),
    showIcon: true,
    inputLabel: (
      <>
        <span className="text-sm">{t("modal.secretKey.inputLabel")}</span>{" "}
        <span className="text-xs text-muted-foreground">
          {t("modal.secretKey.inputLabelOptional")}
        </span>
      </>
    ),
  };

  return modalProps;
};
