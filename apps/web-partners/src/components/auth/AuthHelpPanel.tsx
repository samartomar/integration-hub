import { useState } from "react";

export type AuthHelpType =
  | "API_KEY_HEADER"
  | "API_KEY_QUERY"
  | "BASIC"
  | "BEARER"
  | "JWT"
  | "MTLS";

type SecurityLevel = "Low" | "Medium" | "High" | "Very High";

interface AuthHelpContent {
  title: string;
  description: string;
  typicalUsage?: string;
  flow?: string[];
  requiredFields: string[];
  securityNotes: string[];
  exampleRequest?: string;
  securityLevel: SecurityLevel;
}

const SECURITY_BADGE_STYLES: Record<SecurityLevel, string> = {
  Low: "bg-amber-100 text-amber-800 border-amber-200",
  Medium: "bg-sky-100 text-sky-800 border-sky-200",
  High: "bg-emerald-100 text-emerald-800 border-emerald-200",
  "Very High": "bg-violet-100 text-violet-800 border-violet-200",
};

export const AUTH_HELP_CONTENT: Record<AuthHelpType, AuthHelpContent> = {
  API_KEY_HEADER: {
    title: "API Key (Header)",
    description:
      "Used when the vendor expects a static API key in a request header.",
    typicalUsage: "Legacy vendor APIs or internal partner services.",
    requiredFields: ["Header Name (example: Api-Key)", "API Key Value"],
    exampleRequest: "GET /endpoint\nApi-Key: abc123",
    securityNotes: [
      "API keys must be stored encrypted.",
      "Never log API keys.",
      "Prefer JWT or mTLS for high-security integrations.",
    ],
    securityLevel: "Medium",
  },
  API_KEY_QUERY: {
    title: "API Key (Query Parameter)",
    description:
      "Used when the vendor requires the API key as a query parameter.",
    requiredFields: ["Parameter name", "API key value"],
    exampleRequest: "GET /endpoint?api_key=abc123",
    securityNotes: [
      "Query parameters may appear in logs.",
      "Avoid for sensitive APIs.",
      "Prefer header-based authentication instead.",
    ],
    securityLevel: "Low",
  },
  BASIC: {
    title: "Basic Authentication",
    description: "Uses HTTP Basic Auth with username and password.",
    requiredFields: ["Username", "Password"],
    exampleRequest: "Authorization: Basic base64(username:password)",
    securityNotes: [
      "Must be used only over HTTPS.",
      "Credentials should be stored encrypted.",
      "Prefer OAuth/JWT for modern integrations.",
    ],
    securityLevel: "Medium",
  },
  BEARER: {
    title: "Bearer Token",
    description: "Uses a static bearer token provided by the vendor.",
    requiredFields: ["Token"],
    exampleRequest:
      "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI...",
    securityNotes: [
      "Tokens should be rotated regularly.",
      "Never log tokens.",
      "For dynamic tokens use JWT Bearer instead.",
    ],
    securityLevel: "Medium",
  },
  JWT: {
    title: "JWT Bearer Token (OAuth Client Credentials)",
    description:
      "The Hub obtains a JWT access token from the vendor's identity provider before calling the API.",
    flow: [
      "Hub requests token from vendor IdP",
      "Vendor IdP returns access_token",
      "Hub calls API with Authorization header",
    ],
    requiredFields: [
      "Token URL",
      "Client ID",
      "Client Secret",
      "Scope (optional)",
    ],
    exampleRequest: "Authorization: Bearer <access_token>",
    securityNotes: [
      "Recommended for enterprise integrations.",
      "Supports token rotation.",
      "Vendor controls access using scopes.",
    ],
    securityLevel: "High",
  },
  MTLS: {
    title: "Mutual TLS (Client Certificate)",
    description:
      "Vendor requires the caller to present a trusted client certificate.",
    flow: [
      "Hub establishes TLS connection",
      "Hub presents client certificate",
      "Vendor validates certificate trust",
    ],
    requiredFields: [
      "Client certificate",
      "Private key",
      "Certificate authority",
    ],
    securityNotes: [
      "Highest security option.",
      "Requires certificate rotation policy.",
      "Usually combined with JWT.",
    ],
    securityLevel: "Very High",
  },
};

interface AuthHelpPanelProps {
  authType: AuthHelpType;
}

export function AuthHelpPanel({ authType }: AuthHelpPanelProps) {
  const content = AUTH_HELP_CONTENT[authType] ?? AUTH_HELP_CONTENT.API_KEY_HEADER;
  const showClientRegistrationHint = authType === "JWT" || authType === "MTLS";
  const [expanded, setExpanded] = useState(false);

  return (
    <aside className="rounded-lg border border-gray-200 bg-gray-50 p-4">
      <div className={`${expanded ? "" : "max-h-[40vh] overflow-hidden"} relative`}>
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">Authentication Guide</h3>
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${SECURITY_BADGE_STYLES[content.securityLevel]}`}
            >
              {content.securityLevel}
            </span>
          </div>

          <div>
            <p className="text-sm font-medium text-gray-900">{content.title}</p>
            <p className="mt-1 text-xs text-gray-600">{content.description}</p>
            {content.typicalUsage && (
              <p className="mt-2 text-xs text-gray-600">
                <span className="font-medium text-gray-700">Typical usage:</span>{" "}
                {content.typicalUsage}
              </p>
            )}
          </div>

          {content.flow && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Flow</p>
              <ol className="mt-2 space-y-1 text-xs text-gray-700 list-decimal list-inside">
                {content.flow.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
          )}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Required Fields
            </p>
            <ul className="mt-2 space-y-1 text-xs text-gray-700 list-disc list-inside">
              {content.requiredFields.map((field) => (
                <li key={field}>{field}</li>
              ))}
            </ul>
          </div>

          {content.exampleRequest && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Example Request
              </p>
              <pre className="mt-2 rounded-md border border-gray-200 bg-white p-2 text-[11px] leading-5 text-gray-700 overflow-x-auto">
                {content.exampleRequest}
              </pre>
            </div>
          )}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Security Notes
            </p>
            <ul className="mt-2 space-y-1 text-xs text-gray-700 list-disc list-inside">
              {content.securityNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-100 p-3 space-y-1">
            <p className="text-xs text-slate-700">
              This authentication profile will be used when the Integration Hub calls
              the vendor endpoint.
            </p>
            {showClientRegistrationHint && (
              <p className="text-xs text-slate-700 font-medium">
                Ensure the vendor has registered the Integration Hub as an authorized
                client.
              </p>
            )}
          </div>
        </div>
        {!expanded && (
          <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-gray-50 to-transparent pointer-events-none" />
        )}
      </div>
      <div className="pt-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs font-medium text-slate-700 hover:text-slate-900 underline"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      </div>
    </aside>
  );
}
