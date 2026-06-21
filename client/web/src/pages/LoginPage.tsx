import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [showPwd, setShowPwd] = useState(false);
  const [showRegPwd, setShowRegPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const { login, register } = useAuth();
  const navigate = useNavigate();

  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const username = (fd.get("username") as string || "").trim();
    const password = (fd.get("password") as string || "").trim();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const username = (fd.get("username") as string || "").trim();
    const email    = (fd.get("email")    as string || "").trim();
    const password = (fd.get("password") as string || "").trim();
    setError("");
    if (!/^[a-zA-Z0-9_-]{3,50}$/.test(username)) {
      setError("Tên đăng nhập chỉ gồm chữ cái, số, _ hoặc - (3–50 ký tự)");
      return;
    }
    if (password.length < 8) {
      setError("Mật khẩu phải có ít nhất 8 ký tự");
      return;
    }
    setLoading(true);
    try {
      await register(username, email, password);
      setTab("login");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng ký thất bại");
    } finally {
      setLoading(false);
    }
  }



  return (
    <div className="bg-background text-on-background min-h-screen flex items-center justify-center p-4 md:p-8 relative overflow-hidden">
      {/* Decorative background blobs */}
      <div className="absolute inset-0 overflow-hidden z-0 pointer-events-none opacity-20">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-primary-container rounded-full filter blur-3xl opacity-70" />
        <div className="absolute top-40 -left-40 w-72 h-72 bg-secondary-container rounded-full filter blur-3xl opacity-70" />
        <div className="absolute -bottom-40 left-20 w-80 h-80 bg-tertiary-container rounded-full filter blur-3xl opacity-70" />
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm z-10 relative overflow-hidden flex flex-col">
        {/* Logo header */}
        <div className="pt-10 pb-6 px-8 flex flex-col items-center border-b border-surface-container-high bg-surface">
          <div className="w-16 h-16 bg-primary-container rounded-full flex items-center justify-center mb-4 text-on-primary-container shadow-sm">
            <span className="material-symbols-outlined text-3xl icon-fill">potted_plant</span>
          </div>
          <h1 className="text-3xl font-bold text-primary">VietCropDoctor</h1>
          <p className="text-base text-on-surface-variant mt-2 text-center">
            Chuyên gia kỹ thuật số về sức khỏe cây trồng
          </p>
        </div>

        {/* Form area */}
        <div className="p-8 bg-surface-container-lowest">
          {/* Tabs */}
          <div className="flex border-b border-outline-variant mb-6">
            <button
              onClick={() => { setTab("login"); setError(""); }}
              className={`flex-1 pb-3 text-center text-xl font-semibold transition-colors ${
                tab === "login"
                  ? "text-primary border-b-2 border-primary font-bold"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              Đăng nhập
            </button>
            <button
              onClick={() => { setTab("register"); setError(""); }}
              className={`flex-1 pb-3 text-center text-xl font-semibold transition-colors ${
                tab === "register"
                  ? "text-primary border-b-2 border-primary font-bold"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              Đăng ký
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-error-container text-on-error-container rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Login form */}
          {tab === "login" && (
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-on-surface mb-2" htmlFor="login-username">
                  Email
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-outline">
                    <span className="material-symbols-outlined text-xl">person</span>
                  </div>
                  <input
                    id="login-username"
                    name="username"
                    type="text"
                    placeholder="your_email@gmail.com"
                    className="w-full pl-10 pr-4 py-3 bg-surface-container-lowest border border-outline rounded focus:ring-2 focus:ring-primary focus:border-primary text-base text-on-surface placeholder:text-outline-variant outline-none transition-shadow"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-sm font-medium text-on-surface" htmlFor="login-password">
                    Mật khẩu
                  </label>
                  <button type="button" className="text-xs font-semibold text-primary hover:opacity-80">
                    Quên mật khẩu?
                  </button>
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-outline">
                    <span className="material-symbols-outlined text-xl">lock</span>
                  </div>
                  <input
                    id="login-password"
                    name="password"
                    type={showPwd ? "text" : "password"}
                    placeholder="Nhập mật khẩu của bạn"
                    className="w-full pl-10 pr-10 py-3 bg-surface-container-lowest border border-outline rounded focus:ring-2 focus:ring-primary focus:border-primary text-base text-on-surface placeholder:text-outline-variant outline-none transition-shadow"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-outline hover:text-on-surface transition-colors"
                  >
                    <span className="material-symbols-outlined text-xl">
                      {showPwd ? "visibility_off" : "visibility"}
                    </span>
                  </button>
                </div>
              </div>

              <div className="flex items-center">
                <input
                  id="remember"
                  name="remember"
                  type="checkbox"
                  className="h-4 w-4 text-primary border-outline rounded"
                />
                <label htmlFor="remember" className="ml-2 text-base text-on-surface-variant">
                  Ghi nhớ đăng nhập
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 bg-primary text-on-primary rounded text-sm font-bold shadow-sm hover:bg-primary-container hover:text-on-primary-container transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
              >
                <span className="material-symbols-outlined">login</span>
                {loading ? "Đang đăng nhập..." : "Đăng nhập"}
              </button>

            </form>
          )}

          {/* Register form */}
          {tab === "register" && (
            <form onSubmit={handleRegister} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-on-surface mb-2" htmlFor="reg-username">
                  Tên đăng nhập
                  <span className="ml-1 text-xs text-on-surface-variant font-normal">(chữ cái, số, _ hoặc -)</span>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-outline">
                    <span className="material-symbols-outlined text-xl">badge</span>
                  </div>
                  <input
                    id="reg-username"
                    name="username"
                    type="text"
                    placeholder="nguyen_van_a"
                    autoComplete="username"
                    className="w-full pl-10 pr-4 py-3 bg-surface-container-lowest border border-outline rounded focus:ring-2 focus:ring-primary focus:border-primary text-base text-on-surface placeholder:text-outline-variant outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-on-surface mb-2" htmlFor="reg-email">
                  Email
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-outline">
                    <span className="material-symbols-outlined text-xl">mail</span>
                  </div>
                  <input
                    id="reg-email"
                    name="email"
                    type="text"
                    placeholder="your_email@gmail.com"
                    className="w-full pl-10 pr-4 py-3 bg-surface-container-lowest border border-outline rounded focus:ring-2 focus:ring-primary focus:border-primary text-base text-on-surface placeholder:text-outline-variant outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-on-surface mb-2" htmlFor="reg-password">
                  Mật khẩu
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-outline">
                    <span className="material-symbols-outlined text-xl">lock</span>
                  </div>
                  <input
                    id="reg-password"
                    name="password"
                    type={showRegPwd ? "text" : "password"}
                    placeholder="Tạo mật khẩu mạnh"
                    className="w-full pl-10 pr-10 py-3 bg-surface-container-lowest border border-outline rounded focus:ring-2 focus:ring-primary focus:border-primary text-base text-on-surface placeholder:text-outline-variant outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowRegPwd((v) => !v)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-outline hover:text-on-surface transition-colors"
                  >
                    <span className="material-symbols-outlined text-xl">
                      {showRegPwd ? "visibility_off" : "visibility"}
                    </span>
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 bg-primary text-on-primary rounded text-sm font-bold shadow-sm hover:bg-primary-container hover:text-on-primary-container transition-colors flex items-center justify-center gap-2 mt-6 disabled:opacity-60"
              >
                <span className="material-symbols-outlined">person_add</span>
                {loading ? "Đang tạo tài khoản..." : "Tạo tài khoản"}
              </button>

              <p className="text-xs text-center text-on-surface-variant">
                Bằng việc đăng ký, bạn đồng ý với{" "}
                <a href="#" className="text-primary hover:underline">Điều khoản dịch vụ</a>{" "}
                và{" "}
                <a href="#" className="text-primary hover:underline">Chính sách bảo mật</a>.
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
