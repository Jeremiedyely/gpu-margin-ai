/**
 * App Header — dark top bar with title and optional session badge.
 */

interface AppHeaderProps {
  sessionId?: string | null;
}

export function AppHeader({ sessionId }: AppHeaderProps) {
  return (
    <div className="bg-slate-800 px-10 py-3 flex items-center justify-end">
      {sessionId && (
        <span className="text-xs text-slate-400 bg-white/[0.08] px-3 py-1 rounded-full font-mono">
          {sessionId}
        </span>
      )}
    </div>
  );
}
