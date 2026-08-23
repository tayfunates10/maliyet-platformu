export async function preserveSuccessfulPrimaryResult<T>(primary: () => Promise<T>, refresh: () => Promise<void>) {
  const result = await primary();
  try {
    await refresh();
    return { result, refreshed: true } as const;
  } catch {
    return { result, refreshed: false } as const;
  }
}
