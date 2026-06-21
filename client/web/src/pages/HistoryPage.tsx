import { useEffect, useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import MainLayout from "@/components/MainLayout";
import { getChatSessions, deleteSession, type ChatSession } from "@/lib/api";
import { formatDiseaseName, getCropName, getDiseaseName } from "@/lib/disease-labels";

const SEVERITY_COLORS: Record<string, string> = {
  healthy:  "bg-[#dcfce3] text-[#166534]",
  mild:     "bg-[#dcfce3] text-[#166534]",
  moderate: "bg-[#fef08a] text-[#854d0e]",
  severe:   "bg-error-container text-on-error-container",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("vi-VN");
  } catch {
    return iso;
  }
}

function getSeverityFromClass(cls: string): string {
  const lower = cls.toLowerCase();
  if (lower.includes("healthy")) return "healthy";
  return "mild";
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    getChatSessions().then((data) => {
      setSessions(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  async function handleDeleteSession(e: MouseEvent, sessionId: string) {
    e.stopPropagation();
    setDeletingId(sessionId);
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } finally {
      setDeletingId(null);
    }
  }

  const filtered = sessions.filter((s) => {
    const term = search.toLowerCase();
    if (!term) return true;
    const disease = s.disease ?? "";
    return (
      getDiseaseName(disease).toLowerCase().includes(term) ||
      getCropName(disease).toLowerCase().includes(term) ||
      s.first_question.toLowerCase().includes(term)
    );
  });

  return (
    <MainLayout>
      <div className="p-4 md:p-8 max-w-6xl mx-auto pb-24">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
          <div>
            <h2 className="text-3xl font-semibold text-on-surface mb-2">Lịch sử Chat AI</h2>
            <p className="text-base text-on-surface-variant">
              Các cuộc hội thoại đã lưu. Nhấn để xem lại hoặc tiếp tục.
            </p>
          </div>
          <div className="relative w-full md:w-56">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline">search</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-base text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
              placeholder="Tìm kiếm bệnh, cây trồng..."
              type="text"
            />
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20 gap-3 text-on-surface-variant">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <span>Đang tải hội thoại...</span>
          </div>
        )}

        {/* Empty state */}
        {!loading && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-20 h-20 rounded-full bg-surface-container-high flex items-center justify-center mb-6">
              <span className="material-symbols-outlined text-on-surface-variant" style={{ fontSize: 40 }}>chat</span>
            </div>
            <h3 className="text-xl font-semibold text-on-surface mb-2">
              {search ? "Không tìm thấy kết quả" : "Chưa có hội thoại nào"}
            </h3>
            <p className="text-on-surface-variant max-w-sm">
              {search
                ? "Thử từ khóa khác."
                : "Hãy chẩn đoán cây trồng và hỏi AI để bắt đầu hội thoại."}
            </p>
          </div>
        )}

        {/* Cards Grid */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((s) => {
              const disease = s.disease ?? "";
              const severity = getSeverityFromClass(disease);
              return (
                <div
                  key={s.session_id}
                  onClick={() => navigate(`/chat?session_id=${s.session_id}${disease ? `&disease=${encodeURIComponent(disease)}` : ""}`)}
                  className="bg-surface-container-lowest rounded-xl border border-outline-variant overflow-hidden hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] transition-all duration-300 flex flex-col group cursor-pointer"
                >
                  {/* Image area */}
                  <div className="relative h-48 w-full bg-surface-variant overflow-hidden">
                    {s.image_url ? (
                      <img
                        src={s.image_url}
                        alt={getDiseaseName(disease)}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                        <span className="material-symbols-outlined text-on-surface-variant" style={{ fontSize: 48 }}>forum</span>
                      </div>
                    )}
                    {/* Message count badge */}
                    <div className="absolute top-3 right-3 bg-surface-container-lowest/90 backdrop-blur-sm rounded-full px-3 py-1 flex items-center gap-1 shadow-sm">
                      <span className="material-symbols-outlined text-primary text-[14px]">chat_bubble</span>
                      <span className="text-xs font-semibold text-on-surface">{s.message_count}</span>
                    </div>
                  </div>

                  {/* Content */}
                  <div className="p-4 flex-1 flex flex-col">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-xs font-semibold text-on-surface-variant flex items-center gap-1">
                        <span className="material-symbols-outlined text-[16px]">calendar_today</span>
                        {formatDate(s.last_at)}
                      </span>
                      {disease && (
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${SEVERITY_COLORS[severity]}`}>
                          {formatDiseaseName(disease).split(" — ")[0]}
                        </span>
                      )}
                    </div>
                    <h3 className="text-xl font-semibold text-on-surface mb-1 line-clamp-1">
                      {disease ? getDiseaseName(disease) : "Hội thoại chung"}
                    </h3>
                    <p className="text-sm text-on-surface-variant mb-4 line-clamp-2 italic">
                      {s.first_question}
                    </p>
                    <div className="mt-auto pt-4 border-t border-outline-variant flex justify-between items-center">
                      <span className="bg-surface-container-high text-on-surface text-xs font-semibold px-2 py-1 rounded-md flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">grass</span>
                        {disease ? getCropName(disease) : "—"}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => handleDeleteSession(e, s.session_id)}
                          disabled={deletingId === s.session_id}
                          className="flex items-center gap-1 text-xs font-semibold text-outline hover:text-error transition-colors disabled:opacity-50"
                          title="Xóa hội thoại"
                        >
                          {deletingId === s.session_id ? (
                            <div className="w-3.5 h-3.5 border-2 border-outline border-t-transparent rounded-full animate-spin" />
                          ) : (
                            <span className="material-symbols-outlined text-[16px]">delete</span>
                          )}
                        </button>
                        <span className="flex items-center gap-1 text-xs font-semibold text-primary">
                          <span className="material-symbols-outlined text-[16px]">chat</span>
                          Tiếp tục
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
