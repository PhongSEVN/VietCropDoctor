import { useNavigate } from "react-router-dom";
import MainLayout from "@/components/MainLayout";

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <MainLayout>
      <div className="flex flex-col items-center justify-center min-h-[70vh] text-center px-4">
        <div className="w-24 h-24 rounded-full bg-surface-container-high flex items-center justify-center mb-6">
          <span className="material-symbols-outlined text-on-surface-variant" style={{ fontSize: 48 }}>
            search_off
          </span>
        </div>
        <h1 className="text-6xl font-bold text-primary mb-2">404</h1>
        <h2 className="text-xl font-semibold text-on-surface mb-2">Trang không tồn tại</h2>
        <p className="text-on-surface-variant mb-8 max-w-sm">
          Đường dẫn bạn truy cập không tồn tại hoặc đã bị xóa.
        </p>
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 px-6 py-3 bg-primary text-on-primary rounded-xl font-semibold hover:opacity-90 transition-opacity"
        >
          <span className="material-symbols-outlined text-[20px]">home</span>
          Về trang chủ
        </button>
      </div>
    </MainLayout>
  );
}
