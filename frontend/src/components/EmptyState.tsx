interface Props {
  message: string;
}

/** DASHBOARD.md section 14: the dashboard must handle incomplete pipelines
 * gracefully and never show fake zeroes or invented insights. This is the
 * one component every "no data yet" case routes through. */
export function EmptyState({ message }: Props) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}
