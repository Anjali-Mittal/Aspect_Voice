interface Props {
    text: string;
}

/** Small "i" icon next to a section heading — hover to see a short
 * explanation of how that section's numbers are calculated. For showing
 * stakeholders (e.g. Hero) the methodology is real and inspectable, not
 * a black box, without cluttering the page with permanent text. */
export function MethodologyTooltip({ text }: Props) {
    return (
        <span className="group relative ml-1.5 inline-flex">
            <button
                type="button"
                className="inline-flex items-center justify-center text-slate-400 hover:text-slate-600"
                aria-label="How this is calculated"
            >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="11" x2="12" y2="16" />
                    <circle cx="12" cy="8" r="1" fill="currentColor" stroke="none" />
                </svg>
            </button>
            <div className="invisible absolute left-0 top-full z-20 mt-2 w-96 rounded-lg border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-600 opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100">
                {text}
            </div>
        </span>
    );
}