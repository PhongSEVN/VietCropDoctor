import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import MainLayout from "@/components/MainLayout";

const SUGGESTIONS = [
  {
    icon: "search",
    title: "Kiểm tra bệnh đạo ôn lúa",
    desc: "Nhận diện sớm các đốm mắt én trên lá lúa.",
  },
  {
    icon: "psychiatry",
    title: "Chẩn đoán bệnh lá cà chua",
    desc: "Phân biệt đốm vòng và mốc sương.",
  },
  {
    icon: "bug_report",
    title: "Cách trị rệp sáp",
    desc: "Giải pháp sinh học và hóa học an toàn.",
  },
  {
    icon: "water_drop",
    title: "Dấu hiệu thiếu đạm",
    desc: "Vàng lá non hay lá già? Hướng dẫn bổ sung.",
  },
];

export default function HomePage() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function handleFile(file: File) {
    if (!file) return;
    const url = URL.createObjectURL(file);
    navigate("/diagnose", { state: { imageUrl: url, fileName: file.name, file } });
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }

  return (
    <MainLayout fullHeight>
      <div className="h-full flex flex-col">
        <div className="flex-1 max-w-7xl mx-auto w-full h-full p-4 md:p-8">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 h-full">
            {/* Left Panel: Upload Zone (40%) */}
            <div className="md:col-span-5 flex flex-col h-full min-h-[320px]">
              <div
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                className={`flex-1 border-2 border-dashed rounded-xl flex flex-col items-center justify-center p-8 text-center cursor-pointer transition-all group relative overflow-hidden ${
                  dragOver
                    ? "border-primary bg-surface-container-low"
                    : "border-outline-variant bg-surface hover:bg-surface-container-low hover:border-primary"
                }`}
              >
                <div className="bg-surface-container rounded-full p-6 mb-6 group-hover:scale-110 transition-transform duration-300">
                  <span
                    className="material-symbols-outlined text-primary icon-fill"
                    style={{ fontSize: "48px" }}
                  >
                    add_photo_alternate
                  </span>
                </div>
                <h2 className="text-xl font-semibold text-on-surface mb-2">
                  Tải lên hình ảnh cây trồng để bắt đầu
                </h2>
                <p className="text-base text-on-surface-variant max-w-[250px]">
                  Kéo thả hoặc nhấp để chọn ảnh chụp rõ nét phần cây bị bệnh (lá, thân, quả).
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  aria-label="Tải lên hình ảnh"
                  className="hidden"
                  onChange={onFileChange}
                />
              </div>
            </div>

            {/* Right Panel: Welcome & Actions (60%) */}
            <div className="md:col-span-7 flex flex-col justify-center py-8 md:pl-8">
              <div className="max-w-2xl">
                {/* Welcome header */}
                <h1
                  className="text-on-surface mb-4 leading-tight"
                  style={{ fontSize: "48px", lineHeight: "56px", fontWeight: 700, letterSpacing: "-0.02em" }}
                >
                  Chào mừng bạn đến với <br />
                  <span className="text-primary">VietCropDoctor</span>.
                </h1>
                <p className="text-lg text-on-surface-variant mb-10 leading-7">
                  Tôi có thể giúp gì cho bạn hôm nay? Tải lên một bức ảnh để chẩn đoán bệnh, hoặc bắt đầu một cuộc trò chuyện để được tư vấn nông nghiệp.
                </p>

                {/* Start chat button */}
                <button
                  onClick={() => navigate("/diagnose")}
                  className="bg-secondary-container text-on-secondary-container rounded-full px-8 py-4 flex items-center gap-3 hover:opacity-90 transition-opacity shadow-sm border border-outline-variant/30 w-full sm:w-auto justify-center mb-16"
                >
                  <span className="material-symbols-outlined">forum</span>
                  <span className="text-xl font-semibold">Bắt đầu trò chuyện tạm thời</span>
                </button>

                {/* Quick suggestions */}
                <div>
                  <h3 className="text-sm font-medium text-on-surface-variant uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px]">bolt</span>
                    Gợi ý nhanh
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {SUGGESTIONS.map((s) => (
                      <div
                        key={s.title}
                        onClick={() => navigate("/diagnose", { state: { prompt: s.title } })}
                        className="bg-surface border border-outline-variant rounded-xl p-5 hover:border-primary hover:shadow-sm transition-all cursor-pointer group"
                      >
                        <div className="flex items-start gap-3">
                          <div className="bg-surface-container-highest text-primary p-2 rounded-lg group-hover:bg-primary-container group-hover:text-on-primary-container transition-colors flex-shrink-0">
                            <span className="material-symbols-outlined">{s.icon}</span>
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-on-surface mb-1">{s.title}</p>
                            <p className="text-xs font-semibold tracking-wider text-on-surface-variant">{s.desc}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
