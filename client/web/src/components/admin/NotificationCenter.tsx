import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ROLE_LABELS, logAudit, sendNotification } from "@/lib/admin-api";
import type { BackendRole, NotificationAudience, NotificationDraft } from "@/types/admin";

const AUDIENCES: { value: NotificationAudience; label: string }[] = [
  { value: "all", label: "Toàn hệ thống" },
  { value: "experts", label: "Tất cả chuyên gia" },
  { value: "group", label: "Nhóm theo vai trò" },
];

const GROUPS: BackendRole[] = ["farmer", "agronomist", "admin"];
const INPUT =
  "h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40";

export function NotificationCenter() {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState<NotificationAudience>("all");
  const [group, setGroup] = useState<BackendRole>("farmer");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    if (!title.trim() || !body.trim()) {
      setError("Vui lòng nhập tiêu đề và nội dung.");
      return;
    }
    const draft: NotificationDraft = {
      title: title.trim(),
      body: body.trim(),
      audience,
      group: audience === "group" ? group : null,
    };
    setSubmitting(true);
    try {
      const res = await sendNotification(draft);
      await logAudit("notification.send", undefined, null, draft);
      setResult(`Đã gửi tới ${res.sent} người nhận.`);
      setTitle("");
      setBody("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi thông báo thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="border-outline-variant bg-surface-container-lowest max-w-2xl">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-on-surface">Gửi thông báo</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSend} className="space-y-3">
          <div>
            <label className="text-xs text-on-surface-variant">Tiêu đề</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label className="text-xs text-on-surface-variant">Nội dung</label>
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} className="min-h-[100px] border-outline-variant bg-surface-container-lowest" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-on-surface-variant">Đối tượng</label>
              <select value={audience} onChange={(e) => setAudience(e.target.value as NotificationAudience)} className={INPUT}>
                {AUDIENCES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
            </div>
            {audience === "group" && (
              <div>
                <label className="text-xs text-on-surface-variant">Nhóm</label>
                <select value={group} onChange={(e) => setGroup(e.target.value as BackendRole)} className={INPUT}>
                  {GROUPS.map((g) => <option key={g} value={g}>{ROLE_LABELS[g]}</option>)}
                </select>
              </div>
            )}
          </div>

          {result && <p className="text-xs text-green-600">{result}</p>}
          {error && <p className="text-xs text-error">{error}</p>}

          <Button type="submit" disabled={submitting}>
            {submitting ? "Đang gửi..." : "Gửi thông báo"}
          </Button>
          <p className="text-[11px] text-on-surface-variant">
            TODO(backend): POST /admin/notifications + kênh đẩy (WebSocket/FCM/email) để giao thông báo thực tế.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
