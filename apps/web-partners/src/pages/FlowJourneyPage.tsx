/**
 * Flow Journey – milestone slides for vendor integration flow.
 * Canonical Explorer → Sandbox → AI Debugger → Runtime Preflight → Canonical Execute.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { PartnerCanonicalExplorerPage } from "./PartnerCanonicalExplorerPage";
import { PartnerSandboxPage } from "./PartnerSandboxPage";
import { PartnerAIDebuggerPage } from "./PartnerAIDebuggerPage";
import { PartnerRuntimePreflightPage } from "./PartnerRuntimePreflightPage";
import { PartnerCanonicalExecutePage } from "./PartnerCanonicalExecutePage";

const MILESTONES = [
  { id: "canonical", label: "Canonical Explorer", component: PartnerCanonicalExplorerPage },
  { id: "sandbox", label: "Sandbox", component: PartnerSandboxPage },
  { id: "ai-debugger", label: "AI Debugger", component: PartnerAIDebuggerPage },
  { id: "preflight", label: "Runtime Preflight", component: PartnerRuntimePreflightPage },
  { id: "execute", label: "Canonical Execute", component: PartnerCanonicalExecutePage },
] as const;

export function FlowJourneyPage() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [shake, setShake] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const progressPercent = ((currentIndex + 1) / MILESTONES.length) * 100;

  const scrollToIndex = useCallback((index: number) => {
    if (index < 0 || index >= MILESTONES.length) return;
    if (hasUnsavedChanges && index > currentIndex) {
      setShake(true);
      setTimeout(() => setShake(false), 500);
      return;
    }
    setCurrentIndex(index);
    scrollRef.current?.children[index]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [currentIndex, hasUnsavedChanges]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const children = Array.from(el.children);
      const scrollTop = el.scrollTop;
      const viewHeight = el.clientHeight;
      for (let i = children.length - 1; i >= 0; i--) {
        const child = children[i] as HTMLElement;
        const top = child.offsetTop;
        if (scrollTop >= top - viewHeight / 2) {
          setCurrentIndex(i);
          break;
        }
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col -mx-3 sm:-mx-6 lg:-mx-8">
      {/* Progress worm */}
      <div className="h-1 bg-gray-200 shrink-0">
        <div
          className="h-full bg-teal-500 transition-all duration-300 ease-out"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Milestone tabs */}
      <div className="flex gap-1 overflow-x-auto py-2 px-3 bg-white border-b border-gray-200 shrink-0">
        {MILESTONES.map((m, i) => (
          <button
            key={m.id}
            type="button"
            onClick={() => scrollToIndex(i)}
            className={`shrink-0 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              currentIndex === i
                ? "bg-teal-100 text-teal-800"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {i + 1}. {m.label}
          </button>
        ))}
      </div>

      {/* Scroll container with snap and ghosting */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto overflow-x-hidden snap-y snap-mandatory"
        style={{ scrollSnapType: "y mandatory" }}
      >
        {MILESTONES.map((m, i) => {
          const Component = m.component;
          const isActive = currentIndex === i;
          const isPrev = i < currentIndex;
          const isNext = i > currentIndex;
          return (
            <section
              key={m.id}
              className="min-h-full w-full snap-start snap-always shrink-0 relative"
              style={{ scrollSnapAlign: "start" }}
            >
              <div
                className={`min-h-full p-4 transition-opacity duration-200 ${
                  isActive ? "opacity-100" : "opacity-10"
                }`}
              >
                <div
                  className={`max-w-6xl mx-auto ${
                    shake && isActive ? "animate-shake" : ""
                  }`}
                >
                  <Component />
                  {isActive && i < MILESTONES.length - 1 && (
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <button
                        type="button"
                        onClick={() => scrollToIndex(i + 1)}
                        className="text-sm font-medium text-teal-600 hover:text-teal-800"
                      >
                        Next: {MILESTONES[i + 1].label} →
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </section>
          );
        })}
      </div>

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
          20%, 40%, 60%, 80% { transform: translateX(4px); }
        }
        .animate-shake {
          animation: shake 0.5s ease-in-out;
        }
      `}</style>
    </div>
  );
}
