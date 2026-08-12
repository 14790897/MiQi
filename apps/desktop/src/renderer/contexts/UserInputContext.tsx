import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import type {
  UserInputCardRequest,
  UserInputResolvedData,
} from '../../shared/ipc';

export type UserInputCardState = 'pending' | 'confirmed' | 'cancelled';

export interface UserInputCardEntry {
  request: UserInputCardRequest;
  state: UserInputCardState;
  /** User's final choice, filled once resolved (issue #646). */
  choiceLabel?: string;
  choiceId?: string;
  resolvedAt?: number;
}

interface UserInputContextValue {
  /** Active (pending) cards keyed by input_id — at most one per turn. */
  pending: Record<string, UserInputCardEntry>;
  /** Resolved cards kept in the message flow for traceability. */
  resolved: Record<string, UserInputCardEntry>;
  /** Send the user's choice back to the backend (blocking tool resolves). */
  resolve: (inputId: string, choiceId: string, choiceLabel: string) => Promise<void>;
}

const UserInputContext = createContext<UserInputContextValue>({
  pending: {},
  resolved: {},
  resolve: async () => {},
});

export function UserInputProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Record<string, UserInputCardEntry>>({});
  const [resolved, setResolved] = useState<Record<string, UserInputCardEntry>>({});
  const pendingRef = useRef<Record<string, UserInputCardEntry>>({});

  const upsertPending = useCallback((entry: UserInputCardEntry) => {
    pendingRef.current = { ...pendingRef.current, [entry.request.input_id]: entry };
    setPending(pendingRef.current);
  }, []);

  const moveToResolved = useCallback(
    (inputId: string, state: UserInputCardState, choiceId?: string, choiceLabel?: string) => {
      const entry = pendingRef.current[inputId];
      if (!entry) return;
      const done: UserInputCardEntry = {
        ...entry,
        state,
        choiceId,
        choiceLabel,
        resolvedAt: Date.now(),
      };
      pendingRef.current = { ...pendingRef.current };
      delete pendingRef.current[inputId];
      setPending(pendingRef.current);
      setResolved((prev) => ({ ...prev, [inputId]: done }));
    },
    [],
  );

  useEffect(() => {
    const miqi = (window as any).miqi;
    if (!miqi?.userInput) return;
    const unsubReq = miqi.userInput.onRequest((data: UserInputCardRequest) => {
      upsertPending({
        request: data,
        state: 'pending',
      });
    });
    const unsubRes = miqi.userInput.onResolved((data: UserInputResolvedData) => {
      if (data.status === 'cancelled') {
        moveToResolved(data.input_id, 'cancelled');
      } else {
        const res = data.resolution ?? {};
        moveToResolved(
          data.input_id,
          'confirmed',
          typeof res.choice_id === 'string' ? res.choice_id : undefined,
          typeof res.choice_label === 'string' ? res.choice_label : undefined,
        );
      }
    });
    return () => {
      unsubReq();
      unsubRes();
    };
  }, [upsertPending, moveToResolved]);

  const resolve = useCallback(
    async (inputId: string, choiceId: string, choiceLabel: string) => {
      const miqi = (window as any).miqi;
      // Optimistic update: the card flips to confirmed/cancelled immediately;
      // backend user_input_resolved will reconcile (idempotent).
      moveToResolved(inputId, choiceId === 'cancel' ? 'cancelled' : 'confirmed', choiceId, choiceLabel);
      try {
        await miqi?.userInput?.resolve(inputId, choiceId, choiceLabel);
      } catch {
        // best-effort: backend resolves via timeout/turn-stop otherwise
      }
    },
    [moveToResolved],
  );

  return (
    <UserInputContext.Provider value={{ pending, resolved, resolve }}>
      {children}
    </UserInputContext.Provider>
  );
}

export function useUserInput() {
  return useContext(UserInputContext);
}
