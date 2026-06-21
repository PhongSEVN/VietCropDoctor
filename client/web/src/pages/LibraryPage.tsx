import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import MainLayout from "@/components/MainLayout";

export default function LibraryPage() {

  return (
    <MainLayout>
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">Thư viện kiến thức</h1> 
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-xl font-semibold mb-2">Bài viết và tài liệu</h2>
            <p className="text-gray-600">Truy cập các bài viết, tài liệu hướng dẫn và nghiên cứu liên quan đến sức khỏe tâm thần.</p>
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
