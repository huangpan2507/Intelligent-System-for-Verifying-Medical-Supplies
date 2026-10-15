import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "./business-i18n";
import Connections from "./Connections";
import History from "./History";
import Schemes from "./Schemes";
import Tasks from "./Tasks";

export default function BusinessPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const tab = location.pathname.includes("/history")
    ? "historyRules"
    : location.pathname.includes("/connections")
      ? "connections"
      : location.pathname.includes("/tasks")
        ? "tasks"
        : "schemes";
  return (
    <main className="h-full overflow-auto">
      <div className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        <header>
          <h1 className="text-2xl font-semibold">{t("business.title")}</h1>
          <p className="mt-2 text-muted-foreground">
            {t("business.description")}
          </p>
        </header>
        <nav className="flex flex-wrap gap-5 border-b pb-4">
          {(["schemes", "connections", "tasks"] as const).map((name) => (
            <Link
              className={
                tab === name
                  ? "font-semibold text-primary"
                  : "text-muted-foreground"
              }
              key={name}
              to={name === "schemes" ? "/business" : `/business/${name}`}
            >
              {t(`business.${name}`)}
            </Link>
          ))}
          <Link className="text-muted-foreground" to="/business/history">
            {t("business.historyRules")}
          </Link>
          <Link
            className="ml-auto text-muted-foreground"
            to="/verification/tasks"
          >
            {t("business.history")}
          </Link>
        </nav>
        {tab === "historyRules" ? (
          <History />
        ) : tab === "connections" ? (
          <Connections />
        ) : tab === "tasks" ? (
          <Tasks />
        ) : (
          <Schemes />
        )}
      </div>
    </main>
  );
}
