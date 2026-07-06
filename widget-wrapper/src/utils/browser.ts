export function getCurrentOrigin(): string {
  return typeof window !== "undefined" ? window.location.origin : "";
}
