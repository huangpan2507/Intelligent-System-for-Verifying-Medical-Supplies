import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "./business-i18n";

/** Keep the configuration summary and errors visible while the editor is folded. */
export default function ConfigurationSection({
  id,
  title,
  summary,
  errors = 0,
  defaultOpen = false,
  children,
}: {
  id: string;
  title: string;
  summary?: string;
  errors?: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen || errors > 0);
  useEffect(() => {
    if (errors > 0) setOpen(true);
  }, [errors]);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="min-w-0 rounded border p-3"
      data-testid={`configuration-section-${id}`}
    >
      <summary className="cursor-pointer">
        <span className="font-medium">{title}</span>
        {errors > 0 && (
          <span role="alert" className="ml-2 text-sm text-destructive">
            {t("business.lookup.errors", { count: errors })}
          </span>
        )}
        <p className="mt-1 break-words text-xs text-muted-foreground">
          {summary || t("business.lookup.none")}
        </p>
      </summary>
      <div className="mt-3 min-w-0 space-y-3">{children}</div>
    </details>
  );
}
