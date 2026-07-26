import { useState, useCallback, useRef } from 'react';

/**
 * Provides a `saved` state and a `markSaved()` trigger with auto-reset.
 * Pattern used across ~18 feature pages:
 *   setSaved(true); setTimeout(() => setSaved(false), 2000);
 */
export function useSaveFeedback(resetDelay = 2000) {
  const [saved, setSaved] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const markSaved = useCallback(() => {
    setSaved(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setSaved(false), resetDelay);
  }, [resetDelay]);

  return { saved, markSaved };
}
