import { useState, useEffect } from "react";
import { sessionStore } from "./sessionStore";

/**
 * Hook to subscribe to sessionStore and re-render when sessionExpired or lastError changes.
 */
export function useSessionStore(): { sessionExpired: boolean; lastError: string | null } {
  const [state, setState] = useState(() => ({
    sessionExpired: sessionStore.sessionExpired,
    lastError: sessionStore.lastError,
  }));

  useEffect(() => {
    const unsubscribe = sessionStore.subscribe(() => {
      setState({
        sessionExpired: sessionStore.sessionExpired,
        lastError: sessionStore.lastError,
      });
    });
    return unsubscribe;
  }, []);

  return state;
}
