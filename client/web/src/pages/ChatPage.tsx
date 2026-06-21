import { Suspense, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import MainLayout from "@/components/MainLayout";
import Markdown from "@/components/Markdown";
import { chatWithDisease, getSessionMessages, getHistoryEntry, type Citation } from "@/lib/api";
import Citations from "@/components/Citations";
import { formatDiseaseName, getCropName, getDiseaseName } from "@/lib/disease-labels";
import { useAuth } from "@/lib/auth";
import { useProfile } from "@/lib/profile-context";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Citation[];
}

const SEVERITY_COLORS: Record<string, string> = {
  healthy:  "bg-[#dcfce3] text-[#166534]",
  mild:     "bg-[#dcfce3] text-[#166534]",
  moderate: "bg-[#fef08a] text-[#854d0e]",
  severe:   "bg-error-container text-on-error-container",
};

function generateSessionId() {
  return Math.random().toString(36).slice(2);
}

function ChatUI() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { profile } = useProfile();
  const [searchParams] = useSearchParams();
  const urlSessionId = searchParams.get("session_id");
  const historyId    = searchParams.get("id");
  const sessionId    = useRef(urlSessionId ?? generateSessionId());

  const [disease, setDisease]           = useState(searchParams.get("disease") ?? "");
  const [imageUrl, setImageUrl]         = useState<string | null>(null);
  const [messages, setMessages]         = useState<Message[]>([]);
  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [historyLoading, setHistoryLoading] = useState(!!(urlSessionId || historyId));
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (urlSessionId) {
      getSessionMessages(urlSessionId).then((msgs) => {
        // grab image from first message that has one
        const firstWithImg = msgs.find((m) => m.image_url);
        if (firstWithImg?.image_url) setImageUrl(firstWithImg.image_url);

        const realMsgs = msgs.filter(
          (m) => !m.question.startsWith("Phân tích ảnh:")
        );
        if (realMsgs.length > 0) {
          setMessages(
            realMsgs.flatMap((m) => [
              { role: "user" as const,      content: m.question },
              { role: "assistant" as const, content: m.answer   },
            ])
          );
        } else if (disease) {
          setMessages([{ role: "assistant", content: _welcomeMsg(disease) }]);
        }
        setHistoryLoading(false);
      }).catch(() => setHistoryLoading(false));
    } else if (historyId) {
      getHistoryEntry(historyId).then((entry) => {
        if (entry) {
          setDisease(entry.disease_class);
          if (entry.image_url) setImageUrl(entry.image_url);
          setMessages([{ role: "assistant", content: _welcomeMsg(entry.disease_class) }]);
        }
        setHistoryLoading(false);
      }).catch(() => setHistoryLoading(false));
    } else if (disease) {
      setMessages([{ role: "assistant", content: _welcomeMsg(disease) }]);
    }
  }, [urlSessionId, historyId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await chatWithDisease(disease, text, sessionId.current);
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer, sources: res.sources }]);
    } catch (e: unknown) {
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: e instanceof Error ? `Lỗi: ${e.message}` : "Xin lỗi, tôi không thể trả lời lúc này.",
      }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <MainLayout fullHeight>
      <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">

          {/* ── Left Panel: Image & Info ──────────────────────────────────── */}
          <div className="w-full lg:w-[40%] border-r border-outline-variant bg-surface flex flex-col p-6 overflow-y-auto chat-scroll">
            <div className="flex items-center gap-2 mb-6">
              <button
                onClick={() => navigate(-1)}
                className="w-8 h-8 rounded-full hover:bg-surface-container flex items-center justify-center transition-colors"
              >
                <span className="material-symbols-outlined text-on-surface-variant text-[20px]">arrow_back</span>
              </button>
              <h2 className="text-xl font-semibold text-primary flex items-center gap-2">
                <span className="material-symbols-outlined icon-fill">image_search</span>
                Phân tích hình ảnh
              </h2>
            </div>

            {/* Image */}
            {imageUrl ? (
              <div className="relative w-full aspect-square rounded-xl overflow-hidden border border-outline-variant bg-surface-container-lowest shadow-[0_8px_30px_rgba(0,107,44,0.06)] mb-6">
                <img src={imageUrl} alt="Ảnh cây trồng" className="w-full h-full object-cover" />
                <div className="absolute top-4 left-4 w-4 h-4 border-t-2 border-l-2 border-primary" />
                <div className="absolute top-4 right-4 w-4 h-4 border-t-2 border-r-2 border-primary" />
                <div className="absolute bottom-4 left-4 w-4 h-4 border-b-2 border-l-2 border-primary" />
                <div className="absolute bottom-4 right-4 w-4 h-4 border-b-2 border-r-2 border-primary" />
              </div>
            ) : (
              <div className="w-full aspect-square rounded-xl border-2 border-dashed border-outline-variant bg-surface-container-lowest mb-6 flex flex-col items-center justify-center gap-3">
                <span className="material-symbols-outlined text-on-surface-variant" style={{ fontSize: 48 }}>image_not_supported</span>
                <p className="text-sm text-on-surface-variant">Không có ảnh</p>
              </div>
            )}

            {/* Disease info */}
            {disease && (
              <div className="bg-surface-container-low rounded-xl p-4 border border-outline-variant">
                <div className="mb-3">
                  <span className={`inline-block px-2 py-1 rounded-full text-xs font-semibold mb-2 ${SEVERITY_COLORS["mild"]}`}>
                    Đã chẩn đoán
                  </span>
                  <h3 className="text-2xl font-semibold text-on-surface">{getDiseaseName(disease)}</h3>
                  <p className="text-sm text-on-surface-variant italic">{disease}</p>
                </div>
                <div className="mt-4 pt-4 border-t border-outline-variant/50">
                  <span className="text-xs font-semibold text-on-surface-variant block mb-1">Cây trồng</span>
                  <span className="text-base text-on-surface font-medium flex items-center gap-1">
                    <span className="material-symbols-outlined text-sm text-primary">grass</span>
                    {getCropName(disease)}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* ── Right Panel: Chat ─────────────────────────────────────────── */}
          <div className="w-full lg:w-[60%] flex flex-col bg-surface-bright relative">
            <div className="flex-1 overflow-y-auto chat-scroll p-4 lg:p-8 flex flex-col gap-6">
              {historyLoading && (
                <div className="flex items-center justify-center py-12 gap-3 text-on-surface-variant">
                  <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm">Đang tải hội thoại...</span>
                </div>
              )}

              {!historyLoading && messages.map((msg, i) => (
                <div key={i}>
                  {msg.role === "assistant" && (
                    <div className="flex gap-4 max-w-[85%]">
                      <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary shrink-0 mt-1 shadow-sm">
                        <span className="material-symbols-outlined text-sm">smart_toy</span>
                      </div>
                      <div className="bg-surface border border-outline-variant rounded-2xl rounded-tl-sm p-4 text-on-surface shadow-[0_2px_10px_rgba(0,0,0,0.02)]">
                        <MessageContent content={msg.content} />
                        {msg.sources && <Citations citations={msg.sources} />}
                      </div>
                    </div>
                  )}

                  {msg.role === "user" && (
                    <div className="flex gap-4 max-w-[85%] self-end ml-auto flex-row-reverse">
                      <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary text-xs font-bold shrink-0 mt-1 overflow-hidden shadow-sm">
                        {profile?.avatar_url ? (
                          <img src={profile.avatar_url} alt="avatar" className="w-full h-full object-cover" />
                        ) : (
                          user?.username?.[0]?.toUpperCase() ?? "U"
                        )}
                      </div>
                      <div className="bg-primary/10 border border-primary/20 rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
                        <p className="text-on-surface text-sm whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex gap-4 max-w-[85%]">
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary shrink-0 mt-1 shadow-sm">
                    <span className="material-symbols-outlined text-sm">smart_toy</span>
                  </div>
                  <div className="bg-surface border border-outline-variant rounded-2xl rounded-tl-sm px-5 py-4 flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-2 h-2 bg-primary rounded-full animate-bounce" />
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="p-4 bg-surface-bright border-t border-outline-variant shrink-0">
              <div className="max-w-3xl mx-auto relative">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                  disabled={loading}
                  className="w-full bg-surface border border-outline-variant text-on-surface rounded-full py-3 pl-5 pr-12 focus:ring-2 focus:ring-primary/50 focus:border-primary focus:outline-none shadow-sm transition-all text-base disabled:opacity-50"
                  placeholder="Hỏi thêm về triệu chứng, nguyên nhân, cách phòng trị..."
                />
                <button
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                  className="absolute inset-y-1 right-1 w-10 h-10 bg-primary text-on-primary rounded-full flex items-center justify-center hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
                >
                  <span className="material-symbols-outlined text-sm">send</span>
                </button>
              </div>
              <p className="text-center mt-2 text-xs font-semibold text-on-surface-variant">
                VietCropDoctor có thể mắc sai lầm. Hãy luôn tham khảo thêm ý kiến kỹ sư nông nghiệp địa phương.
              </p>
            </div>
          </div>

        </div>
      </div>
    </MainLayout>
  );
}

function _welcomeMsg(disease: string) {
  return `Ảnh của bạn cho thấy dấu hiệu của **${formatDiseaseName(disease)}**.\n\nBạn muốn biết thêm điều gì? Tôi có thể giải thích triệu chứng, nguyên nhân hoặc cách phòng trị bệnh này.`;
}

function MessageContent({ content }: { content: string }) {
  return <Markdown content={content} className="text-base leading-relaxed space-y-2" />;
}

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center gap-3 text-on-surface-variant">
        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span>Đang tải...</span>
      </div>
    }>
      <ChatUI />
    </Suspense>
  );
}
