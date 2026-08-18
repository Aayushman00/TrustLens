import { ApiError } from "../api/client";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.code === "UNKNOWN" ? error.message : `${error.code}: ${error.message}`;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

export default function ErrorNotice({ error }: { error: unknown }) {
  if (error == null) return null;
  return <div className="notice notice-error">{errorMessage(error)}</div>;
}
