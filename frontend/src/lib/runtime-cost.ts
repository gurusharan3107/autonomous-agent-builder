export function runtimeCostDisplay(
  value: number | null | undefined,
  runtimeSdk?: string | null,
  provider?: string | null,
  observability?: Record<string, unknown> | null,
): string {
  const numericValue = Number(value ?? 0);
  if (numericValue > 0) return `$${numericValue.toFixed(4)}`;
  const costSource = String(observability?.cost_source ?? "");
  if (
    costSource === "subscription_unmetered" ||
    provider === "codex_subscription" ||
    String(runtimeSdk ?? "").startsWith("codex")
  ) {
    return "subscription";
  }
  return "$0.0000";
}

export function estimatedCostDisplay(value: number | null | undefined): string {
  const numericValue = Number(value ?? 0);
  if (numericValue <= 0) return "$0.000000";
  if (numericValue < 0.0001) return `$${numericValue.toFixed(6)}`;
  return `$${numericValue.toFixed(4)}`;
}
