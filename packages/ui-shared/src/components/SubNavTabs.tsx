type SubNavTab = {
  id: string;
  label: string;
  countBadge?: number;
};

type SubNavTabsProps = {
  value: string;
  items: SubNavTab[];
  onChange: (id: string) => void;
};

export function SubNavTabs({ value, items, onChange }: SubNavTabsProps) {
  return (
    <div className="overflow-x-auto -mx-px">
      <div className="flex gap-2 sm:gap-3 border-b border-slate-200 min-w-max">
        {items.map((item) => {
          const active = item.id === value;
          return (
            <button
              key={item.id}
              type="button"
              className={
                active
                  ? "relative -mb-px px-3 py-2 sm:pb-2 sm:pt-0 text-sm border-b-2 border-slate-900 text-slate-900 font-medium transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center"
                  : "relative -mb-px px-3 py-2 sm:pb-2 sm:pt-0 text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center"
              }
              onClick={() => onChange(item.id)}
            >
            {item.label}
            {typeof item.countBadge === "number" && (
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                {item.countBadge}
              </span>
            )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
