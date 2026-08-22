export function transitionNullableValue(enabled, currentValue, createEnabledValue) {
  if (!enabled) return null;
  if (currentValue !== null && currentValue !== undefined) return currentValue;
  return createEnabledValue();
}
