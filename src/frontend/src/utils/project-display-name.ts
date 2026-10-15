import type { TFunction } from "i18next";
import type { FolderType, ProjectListType } from "@/pages/MainPage/entities";

type ProjectNameTranslator = (
  key: "project.ownedBy",
  options: { name: string; owner: string },
) => string;

export const getProjectDisplayName = (
  project: Pick<FolderType, "id" | "name" | "owner_username" | "is_owner">,
  t: ProjectNameTranslator,
): string => {
  if (project.is_owner !== false || !project.owner_username) {
    return project.name;
  }

  return t("project.ownedBy", {
    name: project.name,
    owner: project.owner_username,
  });
};

export const getDefaultProjectId = (
  projects: ProjectListType[],
  defaultProjectName: string,
): string | undefined => {
  return (
    projects.find(
      (project) => project.is_owner && project.name === defaultProjectName,
    ) ??
    projects.find((project) => project.is_owner) ??
    projects.find((project) => project.name === defaultProjectName) ??
    projects[0]
  )?.id;
};

/** Localized labels only; editable names and saved project data keep their original values. */
export const getProjectDisplayLabel = (
  project: Pick<FolderType, "id" | "name" | "owner_username" | "is_owner">,
  t: TFunction,
): string => {
  const name =
    project.name === "Starter Project"
      ? t("project.starterName")
      : project.name === "New Project"
        ? t("project.newName")
        : project.name;
  return getProjectDisplayName({ ...project, name }, t);
};
