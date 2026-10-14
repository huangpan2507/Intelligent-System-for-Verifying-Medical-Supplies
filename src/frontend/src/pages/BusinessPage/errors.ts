import axios from "axios";

export function businessError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (detail !== undefined)
      return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return error instanceof Error ? error.message : String(error);
}
