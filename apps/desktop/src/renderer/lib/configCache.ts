let cachedConfig: Record<string, unknown> | null = null;
let cachedAt = 0;
let inflightConfig: Promise<Record<string, unknown>> | null = null;
let generation = 0;

// Short TTL so config saved from tabs that don't invalidate the cache
// (e.g. providers/channels/workspace) becomes visible without a full restart.
const CACHE_TTL_MS = 5000;

/** Share a single config.get() across tabs so entering settings feels instant. */
export function getCachedConfig(): Promise<Record<string, unknown>> {
  if (cachedConfig && Date.now() - cachedAt < CACHE_TTL_MS) {
    return Promise.resolve(cachedConfig);
  }
  if (!inflightConfig) {
    const requestGeneration = generation;
    inflightConfig = window.miqi.config
      .get()
      .then((cfg) => {
        const result = cfg ?? {};
        if (requestGeneration === generation) {
          cachedConfig = result;
          cachedAt = Date.now();
          inflightConfig = null;
        }
        return result;
      })
      .catch((error) => {
        if (requestGeneration === generation) inflightConfig = null;
        throw error;
      });
  }
  return inflightConfig;
}

export function invalidateConfigCache(): void {
  cachedConfig = null;
  cachedAt = 0;
  inflightConfig = null;
  generation += 1;
}
