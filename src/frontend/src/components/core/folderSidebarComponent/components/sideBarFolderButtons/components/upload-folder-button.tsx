import IconComponent from "@/components/common/genericIconComponent";
import ShadTooltip from "@/components/common/shadTooltipComponent";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/pages/BusinessPage/business-i18n";

export const UploadFolderButton = ({ onClick, disabled }) => {
  const { t } = useTranslation();
  return (
    <ShadTooltip content={t("folder.uploadFlow")} styleClasses="z-50">
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 border-0 text-muted-foreground hover:bg-muted"
        onClick={onClick}
        data-testid="upload-project-button"
        aria-label={t("folder.uploadFlow")}
        disabled={disabled}
      >
        <IconComponent name="Upload" className="h-4 w-4" />
      </Button>
    </ShadTooltip>
  );
};
