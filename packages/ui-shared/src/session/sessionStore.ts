/**
 * Session/connection store for tracking auth/backend failures.
 * Uses a simple subscribe pattern (no MobX) so React components can re-render on change.
 */

type Listener = () => void;

class SessionStore {
  sessionExpired = false;
  lastError: string | null = null;
  private listeners = new Set<Listener>();

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((l) => l());
  }

  markExpired(message?: string): void {
    this.sessionExpired = true;
    this.lastError = message ?? null;
    this.notify();
  }

  clear(): void {
    this.sessionExpired = false;
    this.lastError = null;
    this.notify();
  }
}

export const sessionStore = new SessionStore();
