/** Patch console.error and console.warn, and capture uncaught errors. */

import { addEntry } from "./debugStore";
import { isDebugPanelEnabled } from "./debugStore";

let installed = false;

export function installConsoleCapture(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  const origError = console.error;
  const origWarn = console.warn;

  console.error = function (...args: unknown[]) {
    if (isDebugPanelEnabled()) addEntry("error", args);
    origError.apply(console, args);
  };

  console.warn = function (...args: unknown[]) {
    if (isDebugPanelEnabled()) addEntry("warn", args);
    origWarn.apply(console, args);
  };

  window.addEventListener("error", (e) => {
    if (!isDebugPanelEnabled()) return;
    addEntry("error", [
      `Uncaught: ${e.message}`,
      e.filename ? `  at ${e.filename}:${e.lineno ?? "?"}:${e.colno ?? "?"}` : "",
      e.error?.stack ?? "",
    ]);
  });

  window.addEventListener("unhandledrejection", (e) => {
    if (!isDebugPanelEnabled()) return;
    const err = e.reason;
    const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    const stack = err instanceof Error ? err.stack : "";
    addEntry("error", [`Unhandled rejection: ${msg}`, stack]);
  });
}
