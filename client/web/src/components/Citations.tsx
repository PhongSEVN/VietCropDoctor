import type { Citation } from "@/lib/api";

interface CitationsProps {
  citations: Citation[];
}

/**
 * Renders grouped source citations under an assistant message:
 * a disease title plus clickable links to the original web sources.
 */
export default function Citations({ citations }: CitationsProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-outline-variant/40 space-y-2">
      <p className="flex items-center gap-1 text-xs font-medium text-on-surface-variant">
        <span className="material-symbols-outlined text-[14px]">menu_book</span>
        Nguồn tham khảo
      </p>
      {citations.map((citation, i) => (
        <div key={i} className="text-xs leading-relaxed">
          <span className="text-on-surface">{citation.title}</span>
          {citation.links.length > 0 && (
            <span className="flex flex-wrap gap-x-3 gap-y-1 mt-0.5">
              {citation.links.map((link, j) =>
                link.url ? (
                  <a
                    key={j}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 text-primary hover:underline break-all"
                  >
                    {link.label}
                    <span className="material-symbols-outlined text-[12px]">open_in_new</span>
                  </a>
                ) : (
                  <span key={j} className="text-on-surface-variant">
                    {link.label}
                  </span>
                ),
              )}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
