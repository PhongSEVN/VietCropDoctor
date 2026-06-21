"""Mở rộng qrels: quét toàn bộ tài liệu thật trong Qdrant, gán NHÃN GỢI Ý.

Vì sao cần: bộ qrels mẫu chỉ phán xét 10 tài liệu, nên mọi doc khác retriever
trả về (cẩm nang chung `crop/__chung__`, các bệnh ngoài 10 doc) bị coi là 0 →
NDCG bị kéo thấp oan. Script này quét hết doc thật trong collection và đề xuất
nhãn theo luật để bạn chỉ việc SOÁT lại.

Luật gợi ý (cho từng câu in-scope, dựa trên cây của tài liệu đúng = nhãn 3):
  - đúng tài liệu (đang là 3)          → 3
  - tài liệu CHUNG cùng cây / pdf       → 2
  - bệnh khác CÙNG cây                  → 2
  - bệnh / cẩm nang KHÁC cây            → 1

Đây là NHÃN GỢI Ý theo luật, KHÔNG phải nhãn vàng. Script:
  - GIỮ NGUYÊN mọi nhãn bạn đã gán (không ghi đè), chỉ THÊM doc chưa có.
  - Ghi ra FILE MỚI `qrels_expanded.csv` — bạn soát xong mới thay cho qrels.csv.

Chạy (trên host):
    python src/expand_qrels.py --qdrant-host localhost
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from doc_mapping import doc_id_from_source
from paths import ensure_rag_importable

EVAL_DIR = Path(__file__).resolve().parent.parent


def load_queries(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_qrels(path: Path) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            qrels.setdefault(row["query_id"], {})[row["doc_id"]] = int(row["relevance"])
    return qrels


def discover_doc_ids(host: str | None, port: int | None) -> set[str]:
    """Lấy tập doc_id thật trong Qdrant (suy từ đường dẫn source của mọi chunk)."""
    ensure_rag_importable()
    from rag.core.config import get_settings
    from rag.vectorstore.qdrant_service import QdrantService

    s = get_settings()
    qd = QdrantService(
        host=host or s.qdrant_host,
        port=port or s.qdrant_port,
        collection_name=s.qdrant_collection,
        vector_size=s.embedding_vector_size,
    )
    if not qd.health_check():
        raise RuntimeError(
            f"Không kết nối được Qdrant tại {host or s.qdrant_host}:{port or s.qdrant_port}. "
            "Trên host hãy thêm: --qdrant-host localhost"
        )
    docs: set[str] = set()
    for r in qd.scroll_all():
        d = doc_id_from_source(r.get("source", ""))
        if d:
            docs.add(d)
    return docs


def _exact_doc_and_crop(rels: dict[str, int]) -> tuple[str, str] | None:
    """Tài liệu đúng (nhãn cao nhất) và cây của nó. None nếu không có nhãn."""
    if not rels:
        return None
    exact = max(rels.items(), key=lambda kv: kv[1])[0]
    crop = exact.split("/", 1)[0]
    return exact, crop


def suggest_label(doc_id: str, exact_doc: str, target_crop: str, strict: bool = False) -> int:
    """Gán nhãn gợi ý cho 1 doc với 1 câu hỏi.

    Lỏng (mặc định): đúng=3, cùng cây=2, cẩm nang cùng cây/pdf=2, khác cây=1.
    Chặt (--strict):  đúng=3, cùng cây bệnh khác=1, cẩm nang cùng cây/pdf=2,
                      KHÁC CÂY=0 (để NDCG phân biệt được các cấu hình).
    """
    if doc_id == exact_doc:
        return 3
    crop = doc_id.split("/", 1)[0]
    is_general = doc_id.endswith("/__chung__")
    if strict:
        if is_general:
            return 2 if (crop == target_crop or crop == "pdf") else 0
        return 1 if crop == target_crop else 0
    if is_general:
        return 2 if (crop == target_crop or crop == "pdf") else 1
    return 2 if crop == target_crop else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="Mở rộng qrels với nhãn gợi ý")
    p.add_argument("--data-dir", type=Path, default=EVAL_DIR / "data")
    p.add_argument("--qrels-in", type=Path, default=None,
                   help="qrels nguồn để lấy tài liệu đúng (mặc định data/qrels.csv)")
    p.add_argument("--out", type=Path, default=None, help="file ra (mặc định tuỳ chế độ)")
    p.add_argument("--strict", action="store_true",
                   help="luật chặt: khác cây=0, cùng cây=1, đúng=3 (NDCG phân biệt rõ hơn)")
    p.add_argument("--qdrant-host", default=None)
    p.add_argument("--qdrant-port", type=int, default=None)
    args = p.parse_args()

    queries = load_queries(args.data_dir / "queries.csv")
    qrels = load_qrels(args.qrels_in or (args.data_dir / "qrels.csv"))
    default_out = "qrels_strict.csv" if args.strict else "qrels_expanded.csv"
    out_path = args.out or (args.data_dir / default_out)

    print("Đang quét tài liệu thật trong Qdrant…", flush=True)
    try:
        universe = discover_doc_ids(args.qdrant_host, args.qdrant_port)
    except RuntimeError as exc:
        print(f"\nLỖI: {exc}", file=sys.stderr)
        return 3
    print(f"  Tìm thấy {len(universe)} tài liệu (doc_id) trong collection.")

    rows: list[tuple[str, int, str, int]] = []
    added = kept = 0
    skipped_queries: list[str] = []

    for q in queries:
        qid = q["query_id"]
        if q["type"] != "in_scope":
            continue  # câu OOS: toàn nhãn 0, không thêm dòng
        existing = qrels.get(qid, {})
        info = _exact_doc_and_crop(existing)
        if info is None:
            skipped_queries.append(qid)
            continue
        exact_doc, target_crop = info

        if args.strict:
            # sinh lại sạch theo luật chặt; chỉ giữ doc có relevance >= 1
            merged = {}
            for doc in universe:
                lbl = suggest_label(doc, exact_doc, target_crop, strict=True)
                if lbl >= 1:
                    merged[doc] = lbl
            merged.setdefault(exact_doc, 3)
            added += len(merged)
        else:
            merged = dict(existing)  # giữ nguyên nhãn đã có
            for doc in universe:
                if doc not in merged:
                    merged[doc] = suggest_label(doc, exact_doc, target_crop)
                    added += 1
                else:
                    kept += 1
        for doc in sorted(merged):
            rows.append((qid, 0, doc, merged[doc]))

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "iteration", "doc_id", "relevance"])
        w.writerows(rows)

    print(f"\nĐã ghi {len(rows)} dòng → {out_path}")
    print(f"  - chế độ: {'CHẶT (khác cây=0)' if args.strict else 'LỎNG (khác cây=1)'}")
    if args.strict:
        print(f"  - sinh lại theo luật, chỉ giữ doc relevance ≥ 1: {added} dòng")
    else:
        print(f"  - giữ nguyên nhãn cũ : {kept}")
        print(f"  - thêm nhãn gợi ý    : {added}")
    if skipped_queries:
        print(f"  ⚠️ bỏ qua (không có nhãn 3 để suy cây): {', '.join(skipped_queries)}")
    print("\n⚠️ NHÃN GỢI Ý theo luật — hãy SOÁT lại rồi thay cho data/qrels.csv:")
    print(f"   1) mở {out_path.name} đối chiếu với results/retrieved_dump.md")
    print("   2) sửa chỗ chưa hợp lý")
    print("   3) thay cho data/qrels.csv rồi chạy lại run_eval.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
