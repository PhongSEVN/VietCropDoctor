import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import MainLayout from "@/components/MainLayout";
import FeedbackWidget from "@/components/FeedbackWidget";
import Markdown from "@/components/Markdown";
import { predictImage, chatWithDisease, initChatSession, type PredictResult, type Citation } from "@/lib/api";
import Citations from "@/components/Citations";
import { getCropName, getDiseaseName } from "@/lib/disease-labels";

const SEVERITY_LABEL: Record<string, string> = {
  healthy: "Khỏe mạnh",
  mild: "Nhẹ",
  moderate: "Trung bình",
  severe: "Nặng",
};

const SEVERITY_COLORS: Record<string, string> = {
  healthy: "bg-[#dcfce3] text-[#166534]",
  mild: "bg-[#dcfce3] text-[#166534]",
  moderate: "bg-[#fef08a] text-[#854d0e]",
  severe: "bg-error-container text-on-error-container",
};

function toPercent(val: number): number {
  return val > 1 ? Math.round(val) : Math.round(val * 100);
}

interface ChatMsg {
  role: "ai" | "user";
  content?: string;
  image?: string;
  fileName?: string;
  result?: PredictResult;
  sources?: Citation[];
}

type DiagPhase =
  | { type: "idle" }
  | { type: "predicting"; imageUrl: string; fileName: string }
  | { type: "done"; result: PredictResult; imageUrl: string; fileName: string }
  | { type: "error"; message: string };

export default function DiagnosePage() {
  const location = useLocation();
  const fileRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useRef(`diag-${Date.now()}-${Math.random().toString(36).slice(2)}`);

  const state = location.state as {
    imageUrl?: string;
    fileName?: string;
    file?: File;
  } | null;

  const [phase, setPhase] = useState<DiagPhase>({ type: "idle" });
  const [messages, setMessages] = useState<ChatMsg[]>([
    { role: "ai", content: "Xin chào! Tôi là VietCropDoctor. Hãy tải lên hình ảnh cây trồng đang gặp vấn đề, tôi sẽ giúp bạn chẩn đoán." },
  ]);
  const [activeTab, setActiveTab] = useState<"overview" | "symptoms" | "treatment">("overview");
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const runPrediction = useCallback(async (file: File, imageUrl: string, fileName: string) => {
    setPhase({ type: "predicting", imageUrl, fileName });
    setMessages((prev) => [...prev, { role: "user", image: imageUrl, fileName }]);
    try {
      const result = await predictImage(file);
      setPhase({ type: "done", result, imageUrl, fileName });
      setMessages((prev) => [...prev, { role: "ai", result }]);
      // Only persist the chat session for a valid crop-leaf image (skip OOD/irrelevant).
      if (result.is_in_distribution !== false) {
        initChatSession(sessionId.current, result.disease, result.image_url, getDiseaseName(result.disease));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Phân tích thất bại";
      setPhase({ type: "error", message: msg });
      setMessages((prev) => [...prev, { role: "ai", content: `❌ ${msg}. Vui lòng thử lại.` }]);
    }
  }, []);

  const didPredict = useRef(false);
  useEffect(() => {
    if (didPredict.current) return;
    if (state?.file && state.fileName) {
      didPredict.current = true;
      const freshUrl = URL.createObjectURL(state.file);
      runPrediction(state.file, freshUrl, state.fileName);
      // Drop the file from history state so reloading the page does NOT re-run
      // the one-shot prediction. Each re-run generates a new session_id and
      // persists a fresh "Phân tích ảnh" message, so spamming reload was
      // creating many duplicate chat sessions in History.
      const hs = window.history.state;
      if (hs) window.history.replaceState({ ...hs, usr: null }, "");
      // Don't revoke here — React Strict Mode unmounts and remounts in dev,
      // which would revoke the URL before the second mount can use it.
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  async function handleSendChat() {
    const question = chatInput.trim();
    if (!question || chatLoading || phase.type !== "done") return;
    if (phase.result.is_in_distribution === false) return;  // no chat for invalid images
    setChatInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setChatLoading(true);
    try {
      const resp = await chatWithDisease(phase.result.disease, question, sessionId.current, phase.result.image_url);
      setMessages((prev) => [...prev, { role: "ai", content: resp.answer, sources: resp.sources }]);
    } catch {
      setMessages((prev) => [...prev, { role: "ai", content: "Xin lỗi, tôi không thể trả lời lúc này. Vui lòng thử lại." }]);
    } finally {
      setChatLoading(false);
    }
  }

  const result = phase.type === "done" ? phase.result : null;
  const isOOD = result?.is_in_distribution === false;
  const imageUrl = (phase.type === "done" || phase.type === "predicting") ? phase.imageUrl : undefined;

  return (
    <MainLayout fullHeight>
      <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">

          {/* ── Left Panel: Image & Analysis ───────────────────────────────── */}
          <div className="w-full lg:w-[40%] border-r border-outline-variant bg-surface flex flex-col p-6 overflow-y-auto chat-scroll">
            <h2 className="text-xl font-semibold text-primary mb-6 flex items-center gap-2">
              <span className="material-symbols-outlined icon-fill">image_search</span>
              Phân tích hình ảnh
            </h2>

            {imageUrl ? (
              <div className="relative w-full aspect-square rounded-xl overflow-hidden border border-outline-variant bg-surface-container-lowest shadow-[0_8px_30px_rgba(0,107,44,0.06)] mb-6">
                <img src={imageUrl} alt="Ảnh cây trồng" className="w-full h-full object-cover" />
                <div className="absolute top-4 left-4 w-4 h-4 border-t-2 border-l-2 border-primary" />
                <div className="absolute top-4 right-4 w-4 h-4 border-t-2 border-r-2 border-primary" />
                <div className="absolute bottom-4 left-4 w-4 h-4 border-b-2 border-l-2 border-primary" />
                <div className="absolute bottom-4 right-4 w-4 h-4 border-b-2 border-r-2 border-primary" />
                {phase.type === "predicting" && (
                  <div className="absolute inset-0 bg-surface/60 flex items-center justify-center">
                    <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                  </div>
                )}
                {result && (
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-surface/90 backdrop-blur-sm border border-outline-variant px-4 py-2 rounded-full flex items-center gap-2 shadow-lg">
                    <div className="w-6 h-6 rounded-full border-2 border-primary flex items-center justify-center">
                      <span className="material-symbols-outlined text-[14px] text-primary">check</span>
                    </div>
                    {/*<span className="text-sm font-bold text-on-surface">{toPercent(result.confidence)}% Tự tin</span>*/}
                  </div>
                )}
              </div>
            ) : (
              <div
                onClick={() => fileRef.current?.click()}
                className="w-full aspect-square rounded-xl border-2 border-dashed border-outline-variant bg-surface-container-lowest mb-6 flex flex-col items-center justify-center cursor-pointer hover:border-primary hover:bg-surface-container-low transition-all group"
              >
                <div className="bg-surface-container rounded-full p-6 mb-4 group-hover:scale-110 transition-transform duration-300">
                  <span className="material-symbols-outlined text-primary icon-fill" style={{ fontSize: 48 }}>add_photo_alternate</span>
                </div>
                <p className="text-base font-medium text-on-surface">Chọn ảnh để bắt đầu</p>
                <p className="text-sm text-on-surface-variant mt-1">Hoặc kéo thả vào đây</p>
              </div>
            )}

            {result && result.is_in_distribution === false && (
              <div className="bg-amber-50 rounded-xl p-4 border border-amber-300">
                <div className="flex items-start gap-2 text-amber-800 mb-3">
                  <span className="material-symbols-outlined">warning</span>
                  <div>
                    <p className="font-semibold text-sm">Ảnh không hợp lệ</p>
                    <p className="text-xs mt-1">{result.ood_message ?? "Ảnh không giống lá cây trồng (cà phê, lúa, mía, ngô). Vui lòng chụp lại lá cây cận cảnh, rõ nét."}</p>
                  </div>
                </div>
                <button
                  onClick={() => fileRef.current?.click()}
                  className="w-full bg-primary text-on-primary rounded-full py-2 flex items-center justify-center gap-2 text-sm font-semibold hover:opacity-90 transition-opacity"
                >
                  <span className="material-symbols-outlined text-[18px]">upload</span>
                  Tải ảnh khác
                </button>
              </div>
            )}

            {result && result.is_in_distribution !== false && (
              <div className="bg-surface-container-low rounded-xl p-4 border border-outline-variant">
                <div className="mb-3">
                  <span className={`inline-block px-2 py-1 rounded-full text-xs font-semibold mb-2 ${SEVERITY_COLORS[result.severity] ?? SEVERITY_COLORS.moderate}`}>
                    {SEVERITY_LABEL[result.severity] ?? result.severity}
                  </span>
                  <h3 className="text-2xl font-semibold text-on-surface">{getDiseaseName(result.disease)}</h3>
                  <p className="text-sm text-on-surface-variant italic">{result.disease}</p>
                </div>
                <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-outline-variant/50">
                  <div>
                    <span className="text-xs font-semibold text-on-surface-variant block mb-1">Cây trồng</span>
                    <span className="text-base text-on-surface font-medium flex items-center gap-1">
                      <span className="material-symbols-outlined text-sm text-primary">grass</span>
                      {getCropName(result.disease)}
                    </span>
                  </div>
                  <div>
                    {/* <span className="text-xs font-semibold text-on-surface-variant block mb-1">Đồng thuận</span> */}
                    {/* <span className="text-base text-on-surface font-medium">{toPercent(result.agreement_score)}%</span> */}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ── Right Panel: Chat ───────────────────────────────────────────── */}
          <div className="w-full lg:w-[60%] flex flex-col bg-surface-bright relative">
            <div className="flex-1 overflow-y-auto chat-scroll p-4 lg:p-8 flex flex-col gap-6">
              {messages.map((msg, i) => (
                <div key={i}>
                  {/* AI plain text message */}
                  {msg.role === "ai" && !msg.result && (
                    <div className="flex gap-4 max-w-[85%]">
                      <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary shrink-0 mt-1 shadow-sm">
                        <span className="material-symbols-outlined text-sm">smart_toy</span>
                      </div>
                      <div className="bg-surface border border-outline-variant rounded-2xl rounded-tl-sm p-4 text-on-surface shadow-[0_2px_10px_rgba(0,0,0,0.02)]">
                        <Markdown content={msg.content ?? ""} className="text-base leading-relaxed space-y-2" />
                        {msg.sources && <Citations citations={msg.sources} />}
                      </div>
                    </div>
                  )}

                  {/* User image message */}
                  {msg.role === "user" && msg.image && (
                    <div className="flex gap-4 max-w-[85%] self-end ml-auto flex-row-reverse">
                      <div className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface shrink-0 mt-1 border border-outline-variant">
                        <span className="material-symbols-outlined text-sm">person</span>
                      </div>
                      <div className="bg-surface-container-lowest border border-outline-variant rounded-2xl rounded-tr-sm p-3 shadow-sm">
                        <div className="flex items-center gap-2 text-on-surface-variant text-sm font-medium">
                          <span className="material-symbols-outlined text-primary">image</span>
                          <span>{msg.fileName}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* User text message */}
                  {msg.role === "user" && !msg.image && (
                    <div className="flex gap-4 max-w-[85%] self-end ml-auto flex-row-reverse">
                      <div className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface shrink-0 mt-1 border border-outline-variant">
                        <span className="material-symbols-outlined text-sm">person</span>
                      </div>
                      <div className="bg-primary/10 border border-primary/20 rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
                        <p className="text-on-surface text-sm">{msg.content}</p>
                      </div>
                    </div>
                  )}

                  {/* AI — invalid image (OOD): block result, offer re-upload */}
                  {msg.role === "ai" && msg.result && msg.result.is_in_distribution === false && (
                    <div className="flex gap-4 max-w-[95%]">
                      <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center text-white shrink-0 mt-1 shadow-sm">
                        <span className="material-symbols-outlined text-sm">warning</span>
                      </div>
                      <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl rounded-tl-sm p-5 flex-1">
                        <p className="font-semibold text-amber-800">Ảnh không hợp lệ</p>
                        <p className="text-sm text-amber-700 mt-1 mb-4">
                          {msg.result.ood_message ?? "Ảnh không giống lá cây trồng (cà phê, lúa, mía, ngô). Vui lòng chụp lại lá cây cận cảnh, rõ nét, đủ ánh sáng."}
                        </p>
                        <button
                          onClick={() => fileRef.current?.click()}
                          className="bg-primary text-on-primary rounded-full px-4 py-2 flex items-center gap-2 text-sm font-semibold hover:opacity-90 transition-opacity"
                        >
                          <span className="material-symbols-outlined text-[18px]">upload</span>
                          Tải ảnh khác
                        </button>
                      </div>
                    </div>
                  )}

                  {/* AI diagnosis card */}
                  {msg.role === "ai" && msg.result && msg.result.is_in_distribution !== false && (
                    <div className="flex gap-4 max-w-[95%]">
                      <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary shrink-0 mt-1 shadow-sm">
                        <span className="material-symbols-outlined text-sm">smart_toy</span>
                      </div>
                      <div className="bg-surface border-2 border-primary/30 rounded-2xl rounded-tl-sm p-5 text-on-surface shadow-[0_4px_20px_rgba(0,107,44,0.08)] flex-1">
                        <p className="mb-4 text-base">
                          Dựa trên hình ảnh, tôi dự đoán cây nhiễm {" "}
                          <strong className="text-primary">{getDiseaseName(msg.result.disease)}</strong>{" "}
                          {/* với độ tin cậy <strong>{toPercent(msg.result.confidence)}%</strong>. */}
                        </p>

                        <div className="border border-outline-variant rounded-lg overflow-hidden bg-surface-container-lowest">
                          <div className="flex border-b border-outline-variant bg-surface-container-low">
                            {([["overview", "Tổng quan"], ["symptoms", "Triệu chứng"], ["treatment", "Xử trí"]] as const).map(([key, label]) => (
                              <button key={key} onClick={() => setActiveTab(key)}
                                className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === key
                                  ? "font-bold text-primary border-b-2 border-primary bg-surface"
                                  : "text-on-surface-variant hover:bg-surface cursor-pointer"
                                  }`}>
                                {label}
                              </button>
                            ))}
                          </div>
                          <div className="p-4 text-sm space-y-3">
                            {activeTab === "overview" && (
                              <>
                                <p>{msg.result.explanation}</p>
                                {msg.result.top3.length > 0 && (
                                  <div className="mt-2">
                                    <p className="font-semibold text-on-surface mb-2">Top 3 dự đoán:</p>
                                    <div className="space-y-2">
                                      {msg.result.top3.map((item, j) => (
                                        <div key={j} className="flex items-center gap-2">
                                          <span className="text-xs text-on-surface-variant w-24 truncate" title={item.class_name}>{getDiseaseName(item.class_name)}</span>
                                          <div className="flex-1 bg-surface-container rounded-full h-2">
                                            <div className="bg-primary h-2 rounded-full transition-all" style={{ width: `${toPercent(item.confidence)}%` }} />
                                          </div>
                                          <span className="text-xs text-on-surface-variant w-9 text-right">{toPercent(item.confidence)}%</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </>
                            )}
                            {activeTab === "symptoms" && (
                              <>
                                <p className="text-on-surface-variant">{msg.result.explanation}</p>
                                <p className="text-xs text-on-surface-variant italic mt-2">
                                  Hỏi thêm về triệu chứng cụ thể bên dưới ↓
                                </p>
                              </>
                            )}
                            {activeTab === "treatment" && (
                              <>
                                <div className="bg-surface-container p-3 rounded border-l-4 border-primary">
                                  <p className="text-on-surface">{msg.result.severity_advice}</p>
                                </div>
                                <p className="text-xs text-on-surface-variant italic">
                                  Hỏi thêm về liều lượng thuốc, cách phòng ngừa bên dưới ↓
                                </p>
                              </>
                            )}
                          </div>
                        </div>

                        <FeedbackWidget
                          predictedDisease={msg.result.disease}
                          predictedConfidence={msg.result.confidence}
                          imageUrl={msg.result.image_url}
                          sessionId={sessionId.current}
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Typing indicator */}
              {chatLoading && (
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

              <div ref={chatEndRef} />
            </div>

            {/* Input area */}
            <div className="p-4 bg-surface-bright border-t border-outline-variant shrink-0">
              <div className="max-w-3xl mx-auto relative">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      const url = URL.createObjectURL(f);
                      runPrediction(f, url, f.name);
                    }
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="absolute inset-y-0 left-0 pl-3 flex items-center text-outline hover:text-primary transition-colors"
                  title="Tải ảnh mới"
                >
                  <span className="material-symbols-outlined">attach_file</span>
                </button>
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSendChat(); } }}
                  disabled={phase.type !== "done" || chatLoading || isOOD}
                  className="w-full bg-surface border border-outline-variant text-on-surface rounded-full py-3 pl-10 pr-12 focus:ring-2 focus:ring-primary/50 focus:border-primary focus:outline-none shadow-sm transition-all text-base disabled:opacity-50"
                  placeholder={
                    phase.type === "predicting" ? "Đang phân tích ảnh..."
                      : isOOD ? "Vui lòng tải ảnh lá cây hợp lệ để trò chuyện..."
                        : phase.type !== "done" ? "Tải ảnh để bắt đầu..."
                          : "Hỏi thêm về liều lượng thuốc, cách phòng ngừa..."
                  }
                />
                <button
                  onClick={handleSendChat}
                  disabled={phase.type !== "done" || chatLoading || !chatInput.trim() || isOOD}
                  className="absolute inset-y-1 right-1 w-10 h-10 bg-primary text-on-primary rounded-full flex items-center justify-center hover:bg-primary-container hover:text-on-primary-container transition-colors shadow-sm disabled:opacity-50"
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
