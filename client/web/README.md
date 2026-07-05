# React Web — VietCropDoctor Frontend

Giao diện người dùng cho hệ thống chẩn đoán bệnh cây trồng. Xây dựng bằng React 19 + Vite + TailwindCSS 4.

## Port: `3000` (dev server)

## Tech stack

- **React 19** + **TypeScript**
- **Vite** — build tool
- **TailwindCSS 4** — utility-first CSS
- **shadcn/ui** — component library (Radix UI base)
- **React Router v6** — client-side routing
- **Zustand** — state management

## Cài đặt và chạy

```bash
cd client/web
npm install
npm run dev
```

Truy cập: `http://localhost:3000`

## Build production

```bash
npm run build
npm run preview   # preview build local
```

## Cấu trúc

```
src/
├── pages/
│   ├── LoginPage.tsx         Đăng nhập / đăng ký
│   ├── HomePage.tsx          Dashboard tổng quan
│   ├── DiagnosePage.tsx      Upload ảnh → chẩn đoán
│   ├── ChatPage.tsx          Chat với RAG (hỏi đáp)
│   ├── HistoryPage.tsx       Lịch sử chẩn đoán
│   ├── AnalyticsPage.tsx     Dashboard thống kê (admin)
│   └── SettingsPage.tsx      Cài đặt tài khoản
├── components/
│   ├── ui/                   shadcn/ui components
│   ├── DiagnoseCard.tsx      Hiển thị kết quả chẩn đoán
│   └── ConfidenceBar.tsx     Thanh confidence + top-3
├── hooks/
│   ├── useAuth.ts            JWT auth state
│   └── useDiagnose.ts        Upload + polling kết quả
├── services/
│   ├── api.ts                Axios instance, interceptors
│   ├── auth.ts               Login, register, refresh
│   └── diagnose.ts           /predict, /orchestrate calls
├── stores/
│   └── authStore.ts          Zustand auth state
└── types/                    TypeScript interfaces
```

## Biến môi trường

Tạo file `.env.local`:
```env
VITE_API_BASE_URL=http://localhost:8000
```

## Luồng chính

```
1. User login → JWT lưu trong memory (không localStorage)
2. Upload ảnh lá → POST /orchestrate
3. Nhận kết quả: tên bệnh + confidence + lời khuyên tiếng Việt
```

## Proxy (dev)

`vite.config.ts` proxy `/api` → `http://localhost:8000` để tránh CORS khi dev.
