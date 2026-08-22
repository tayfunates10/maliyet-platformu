export function transitionNullableValue<T>(
  enabled: boolean,
  currentValue: T | null | undefined,
  createEnabledValue: () => T,
): T | null;
