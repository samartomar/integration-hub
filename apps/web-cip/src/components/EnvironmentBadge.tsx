/** Environment badge for LOCAL | DEV | STAGE | PROD in header. */

export function EnvironmentBadge() {
  const env =
    import.meta.env.VITE_ENVIRONMENT ||
    (typeof location !== "undefined" && location.hostname.includes("localhost")
      ? "LOCAL"
      : "UNKNOWN");

  const color =
    env === "PROD"
      ? "#b91c1c"
      : env === "STAGE"
        ? "#ea580c"
        : env === "DEV"
          ? "#2563eb"
          : "#6b7280";

  return (
    <span
      style={{
        padding: "2px 8px",
        background: color,
        color: "white",
        fontSize: "10px",
        fontWeight: 600,
        borderRadius: "4px",
        marginLeft: "8px",
        textTransform: "uppercase",
      }}
    >
      {env}
    </span>
  );
}
