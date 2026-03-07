/** Operator Guide - end-to-end flow for current supported feature set. */

import { Link } from "react-router-dom";

const STEPS = [
  { title: "Canonical Explorer", path: "/admin/canonical", desc: "Browse canonical operations and schemas." },
  { title: "Flow Builder", path: "/admin/flow-builder", desc: "Design flow drafts and generate handoff packages." },
  { title: "Sandbox", path: "/admin/sandbox", desc: "Validate requests and test transforms." },
  { title: "AI Debugger", path: "/admin/ai-debugger", desc: "Debug with Bedrock-enhanced analysis." },
  { title: "Runtime Preflight", path: "/admin/runtime-preflight", desc: "Validate canonical envelope before execute." },
  { title: "Canonical Execute", path: "/admin/canonical-execute", desc: "Bridge canonical request to runtime." },
  { title: "Mission Control", path: "/admin/mission-control", desc: "Operational view of transactions (metadata-only)." },
  { title: "Adoption & Readiness", path: "/admin/adoption", desc: "Adoption status, mapping readiness, release bundle." },
];

export function SyntegrisOperatorGuidePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">Operator Guide</h1>
      <p className="text-sm text-gray-600">
        End-to-end flow for the current supported feature set. Supported operations: GET_VERIFY_MEMBER_ELIGIBILITY,
        GET_MEMBER_ACCUMULATORS. Supported vendor pair: LH001 → LH002.
      </p>

      <ol className="list-decimal list-inside space-y-4">
        {STEPS.map((step, i) => (
          <li key={step.path} className="pl-2">
            <Link
              to={step.path}
              className="font-medium text-slate-700 hover:text-slate-900 hover:underline"
            >
              {step.title}
            </Link>
            <p className="text-sm text-gray-600 mt-0.5 ml-6">{step.desc}</p>
          </li>
        ))}
      </ol>

      <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 text-sm text-gray-700">
        <strong>Note:</strong> No automatic apply of mapping changes. All mapping edits require manual code review
        and promotion. See Adoption & Readiness for release bundle and verification checklist.
      </div>
    </div>
  );
}
