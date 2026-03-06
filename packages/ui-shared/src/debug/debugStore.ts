/** Debug panel store - console entries and enabled state. */

const STORAGE_KEY = "integrationHub.debugPanelEnabled";
const MAX_ENTRIES = 200;

export type ConsoleLevel = "error" | "warn";

export interface ConsoleEntry {
  id: string;
  level: ConsoleLevel;
  timestamp: number;
  args: unknown[];
  serialized: string;
}

let entries: ConsoleEntry[] = [];
let idCounter = 0;
const listeners = new Set<() => void>();

function serialize(args: unknown[]): string {
  try {
    return args
      .map((a) => {
        if (a instanceof Error) return `${a.name}: ${a.message}\n${a.stack ?? ""}`;
        if (typeof a === "object" && a !== null) return JSON.stringify(a, null, 0);
        return String(a);
      })
      .join(" ");
  } catch {
    return String(args);
  }
}

function notify() {
  listeners.forEach((f) => f());
}

export function addEntry(level: ConsoleLevel, args: unknown[]): void {
  const entry: ConsoleEntry = {
    id: `e-${++idCounter}-${Date.now()}`,
    level,
    timestamp: Date.now(),
    args,
    serialized: serialize(args),
  };
  entries.unshift(entry);
  if (entries.length > MAX_ENTRIES) entries = entries.slice(0, MAX_ENTRIES);
  notify();
}

export function getEntries(): readonly ConsoleEntry[] {
  return entries;
}

export function clearEntries(): void {
  entries = [];
  notify();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isDebugPanelEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setDebugPanelEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (enabled) {
      localStorage.setItem(STORAGE_KEY, "true");
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    notify();
  } catch {
    /* ignore */
  }
}
