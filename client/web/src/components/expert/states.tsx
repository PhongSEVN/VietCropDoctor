import type { ReactNode } from "react";

/** Centered loading placeholder. */
export function LoadingState({ label = "Đang tải dữ liệu..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant animate-pulse">
      <span className="material-symbols-outlined text-3xl mb-2">progress_activity</span>
      <p className="text-sm">{label}</p>
    </div>
  );
}

/** Error panel with an optional retry. */
export function ErrorState({
  message,
  onRetry,
  hint,
}: {
  message: string;
  onRetry?: () => void;
  hint?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <span className="material-symbols-outlined text-3xl mb-2 text-error">error</span>
      <p className="text-sm text-error max-w-md">{message}</p>
      {hint && <p className="text-xs text-on-surface-variant mt-2 max-w-md">{hint}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 text-sm text-primary hover:underline"
        >
          Thử lại
        </button>
      )}
    </div>
  );
}

/** Empty placeholder for zero results. */
export function EmptyState({
  icon = "inbox",
  title,
  description,
}: {
  icon?: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center text-on-surface-variant">
      <span className="material-symbols-outlined text-4xl mb-2 opacity-60">{icon}</span>
      <p className="text-sm font-medium text-on-surface">{title}</p>
      {description && <p className="text-xs mt-1 max-w-sm">{description}</p>}
    </div>
  );
}
