import { vendorTheme } from "frontend-shared/styles/tokens";

export function ActiveLicenseeBadge({ label }: { label: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
      style={{
        background: vendorTheme.badgeVendorBg,
        color: vendorTheme.badgeVendorText,
      }}
    >
      {label}
    </span>
  );
}
