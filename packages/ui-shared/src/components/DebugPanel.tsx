import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  getEntries,
  clearEntries,
  subscribe,
  isDebugPanelEnabled,
  setDebugPanelEnabled,
  type ConsoleEntry,
} from "../debug/debugStore";

const PANEL_WIDTH = 420;
const DEFAULT_TOP = 60;
const DEFAULT_LEFT_OFFSET = 24;

export interface DebugPanelProps {
  /** Override visibility; when undefined, uses Ctrl+Shift+D and enabled state */
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export const DebugPanel: React.FC<DebugPanelProps> = ({
  isOpen: controlledOpen,
  onOpenChange,
}) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const [entries, setEntries] = useState<readonly ConsoleEntry[]>([]);
  const [enabled, setEnabled] = useState(isDebugPanelEnabled);
  const [position, setPosition] = useState(() => {
    if (typeof window === "undefined") return { top: DEFAULT_TOP, left: 0 };
    return {
      top: DEFAULT_TOP,
      left: window.innerWidth - PANEL_WIDTH - DEFAULT_LEFT_OFFSET,
    };
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0, left: 0, top: 0 });

  const isOpen = controlledOpen ?? internalOpen;
  const setIsOpen = onOpenChange ?? setInternalOpen;

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button, input, label")) return;
    e.preventDefault();
    dragStart.current = { x: e.clientX, y: e.clientY, left: position.left, top: position.top };
    setIsDragging(true);
  }, [position]);

  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => {
      const { x, y, left, top } = dragStart.current;
      const dx = e.clientX - x;
      const dy = e.clientY - y;
      const w = typeof window !== "undefined" ? window.innerWidth : 800;
      const h = typeof window !== "undefined" ? window.innerHeight : 600;
      setPosition({
        left: Math.max(0, Math.min(w - PANEL_WIDTH, left + dx)),
        top: Math.max(0, Math.min(h - 200, top + dy)),
      });
    };
    const onUp = () => setIsDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [isDragging]);

  useEffect(() => {
    setEntries(getEntries());
    setEnabled(isDebugPanelEnabled());
    return subscribe(() => {
      setEntries(getEntries());
      setEnabled(isDebugPanelEnabled());
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "D" && e.ctrlKey && e.shiftKey) {
        e.preventDefault();
        if (onOpenChange) {
          onOpenChange(!(controlledOpen ?? internalOpen));
        } else {
          setInternalOpen((prev) => !prev);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [controlledOpen, internalOpen, onOpenChange]);

  const handleClear = useCallback(() => {
    clearEntries();
  }, []);

  const handleToggleEnabled = useCallback(() => {
    const next = !isDebugPanelEnabled();
    setDebugPanelEnabled(next);
    setEnabled(next);
  }, []);

  if (!isOpen) return null;

  return (
    <div
      className="fixed z-[100] flex flex-col bg-slate-900 text-slate-100 shadow-2xl rounded-lg overflow-hidden"
      style={{
        top: position.top,
        left: position.left,
        width: PANEL_WIDTH,
        height: "min(400px, 60vh)",
      }}
      role="dialog"
      aria-label="Debug console"
    >
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0 cursor-grab active:cursor-grabbing select-none"
        onMouseDown={handleDragStart}
      >
        <h2 className="text-sm font-semibold">Debug Panel</h2>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs">
            <input
              type="checkbox"
              checked={enabled}
              onChange={handleToggleEnabled}
              className="rounded border-slate-600 bg-slate-800 text-teal-500 focus:ring-teal-500"
            />
            <span>Capture errors</span>
          </label>
          <button
            type="button"
            onClick={handleClear}
            className="px-2 py-1 text-xs rounded bg-slate-700 hover:bg-slate-600"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="p-1 rounded hover:bg-slate-700"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      <p className="px-4 py-2 text-xs text-slate-400 border-b border-slate-700">
        Press <kbd className="px-1 py-0.5 rounded bg-slate-800 font-mono text-slate-300">Ctrl+Shift+D</kbd> to toggle
      </p>
      <div className="flex-1 overflow-auto p-3 font-mono text-xs space-y-2 min-h-0">
        {entries.length === 0 ? (
          <p className="text-slate-500">No console errors or warnings captured yet.</p>
        ) : (
          entries.map((e) => (
            <div
              key={e.id}
              className={`rounded px-3 py-2 break-all ${
                e.level === "error" ? "bg-red-900/40 text-red-200" : "bg-amber-900/30 text-amber-200"
              }`}
            >
              <span className="text-slate-400 mr-2">
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
              <span className="font-semibold uppercase">{e.level}</span>
              <pre className="mt-1 whitespace-pre-wrap text-slate-200">{e.serialized}</pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
