import type { SidebarSection } from "@/components/ui/sidebar";
import type en from "@/locales/en.json";

/**
 * Source of truth for the FlowPage's segmented sidebar nav items. Used by
 * both the real ``SidebarSegmentedNav`` and the FlowBuilderWelcome's faux
 * rail so they can never drift apart.
 *
 * Keep this file free of runtime imports — the
 * welcome's component test imports from here and can't tolerate transitive
 * dependencies that pull in ESM-only modules (nanoid, react-i18next, etc.).
 */
export interface SidebarNavItem {
  id: SidebarSection;
  icon: string;
  /** i18n key — feed through ``t(...)`` at the call site. */
  label: Extract<
    keyof typeof en,
    `sidebar.nav.${string}` | "memory.sidebarTitle"
  >;
  /** i18n key — feed through ``t(...)`` at the call site. */
  tooltip: Extract<
    keyof typeof en,
    `sidebar.nav.${string}` | "memory.sidebarTitle"
  >;
}

export const NAV_ITEMS: SidebarNavItem[] = [
  {
    id: "components",
    icon: "component",
    label: "sidebar.nav.components",
    tooltip: "sidebar.nav.components",
  },
  {
    id: "mcp",
    icon: "Mcp",
    label: "sidebar.nav.mcp",
    tooltip: "sidebar.nav.mcp",
  },
  {
    id: "bundles",
    icon: "blocks",
    label: "sidebar.nav.bundles",
    tooltip: "sidebar.nav.bundles",
  },
  {
    id: "versions",
    icon: "History",
    label: "sidebar.nav.versions",
    tooltip: "sidebar.nav.versionHistory",
  },
  {
    id: "agent",
    icon: "Bot",
    label: "sidebar.nav.agent",
    tooltip: "sidebar.nav.agent",
  },
  {
    id: "memories",
    icon: "BrainCog",
    label: "memory.sidebarTitle",
    tooltip: "memory.sidebarTitle",
  },
  {
    id: "traces",
    icon: "Activity",
    label: "sidebar.nav.traces",
    tooltip: "sidebar.nav.traces",
  },
];
