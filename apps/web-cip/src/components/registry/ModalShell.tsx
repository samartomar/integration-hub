interface ModalShellProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  dialogClassName?: string;
  panelClassName?: string;
  contentClassName?: string;
}

export function ModalShell({
  open,
  onClose,
  title,
  children,
  dialogClassName,
  panelClassName,
  contentClassName,
}: ModalShellProps) {
  if (!open) return null;

  const dialogCls = dialogClassName ?? "fixed inset-0 z-50 flex items-center justify-center";
  const panelCls =
    panelClassName ??
    "relative w-full max-w-md bg-white rounded-lg shadow-xl mx-4 max-h-[90vh] overflow-y-auto";
  const contentCls = contentClassName ?? "p-5";

  return (
    <div className={dialogCls}>
      <div
        className="absolute inset-0 bg-black/50"
        aria-hidden
      />
      <div
        className={panelCls}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
          <h2 id="modal-title" className="font-semibold text-gray-900">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className={contentCls}>{children}</div>
      </div>
    </div>
  );
}
