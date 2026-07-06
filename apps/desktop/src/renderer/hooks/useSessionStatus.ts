import { useState, useCallback } from 'react';

export type SessionStatus = 'IN-PROGRESS' | 'PENDING' | 'REVIEW' | 'COMPLETED' | 'CC';

export interface StatusDisplayInfo {
  label: string;
  bg: string;
  color: string;
  cardBg: string;
  cardBorder: string;
}

const STORAGE_KEY = 'miqi:sessionStatuses';

function loadMap(): Record<string, SessionStatus> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveMap(map: Record<string, SessionStatus>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* localStorage unavailable — silently ignore */
  }
}

/** Default status for sessions without a manual override. */
function fallbackStatus(_idx: number): SessionStatus {
  return 'PENDING';
}

export function useSessionStatus() {
  const [map, setMap] = useState<Record<string, SessionStatus>>(loadMap);

  const getStatus = useCallback(
    (sessionKey: string, index: number): SessionStatus => {
      return map[sessionKey] ?? fallbackStatus(index);
    },
    [map],
  );

  const getStatusDisplay = useCallback((status: SessionStatus): StatusDisplayInfo => {
    switch (status) {
      case 'IN-PROGRESS':
        return {
          label: 'IN-PROGRESS',
          bg: 'var(--tag-inprogress-bg)',
          color: 'var(--tag-inprogress-text)',
          cardBg: '#fffbe6',
          cardBorder: '#f0e8c0',
        };
      case 'REVIEW':
        return {
          label: 'REVIEW',
          bg: 'var(--tag-review-bg)',
          color: 'var(--tag-review-text)',
          cardBg: '#fefdf5',
          cardBorder: '#f0e8c0',
        };
      case 'COMPLETED':
        return {
          label: 'COMPLETED',
          bg: 'var(--tag-completed-bg)',
          color: 'var(--tag-completed-text)',
          cardBg: '#f8fcf9',
          cardBorder: '#d0e8d8',
        };
      case 'CC':
        return {
          label: 'CC',
          bg: 'var(--tag-cc-bg)',
          color: 'var(--tag-cc-text)',
          cardBg: '#f8fcf9',
          cardBorder: '#d0e8d8',
        };
      case 'PENDING':
      default:
        return {
          label: 'PENDING',
          bg: '#f0f0ec',
          color: '#888',
          cardBg: '#fafaf9',
          cardBorder: '#e8e8e0',
        };
    }
  }, []);

  const setStatus = useCallback((sessionKey: string, status: SessionStatus) => {
    setMap((prev) => {
      const next = { ...prev, [sessionKey]: status };
      saveMap(next);
      return next;
    });
  }, []);

  const clearStatus = useCallback((sessionKey: string) => {
    setMap((prev) => {
      const next = { ...prev };
      delete next[sessionKey];
      saveMap(next);
      return next;
    });
  }, []);

  return { getStatus, getStatusDisplay, setStatus, clearStatus };
}
