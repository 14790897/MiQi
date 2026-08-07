let cachedConfig: Record<string, unknown> | null = null;
let inflightConfig: Promise<Record<string, unknown>> | null = null;

/** Share a single config.get() across tabs so entering settings feels instant. */
export function getCachedConfig(): Promise<Record<string, unknown>> {
  if (cachedConfig) return Promise.resolve(cachedConfig);
  if (!inflightConfig) {
    inflightConfig = window.miqi.config
      .get()
      .then((cfg) => {
        cachedConfig = cfg ?? {};
        inflightConfig = null;
        return cachedConfig;
      })
      .catch((error) => {
        inflightConfig = null;
        throw error;
      });
  }
  return inflightConfig;
}

export function invalidateConfigCache(): void {
  cachedConfig = null;
  inflightConfig = null;
}
