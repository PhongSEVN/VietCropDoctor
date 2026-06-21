"""Script chính: đánh giá retrieval offline theo test collection (Cranfield).

Chạy (trong container rag-engine, Qdrant đã ingest dữ liệu):
    python src/run_eval.py
    python src/run_eval.py --alphas 0.5,0.7,0.9 --depth 30 --oos-threshold 0.30

Kiểm thử pipeline chấm điểm trên host (không cần Qdrant/torch), dùng run giả lập:
    python src/run_eval.py --self-test

Đầu ra: bảng NDCG@3/5/10 + Wilcoxon + false-trigger ra màn hình, đồng thời lưu
results/ndcg.csv, results/false_trigger.csv, results/wilcoxon.csv, results/report.md.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import sys
from pathlib import Path

import metrics
from doc_mapping import map_chunk_to_doc, rank_documents

METRIC_NAMES = ["ndcg@3", "ndcg@5", "ndcg@10", "mrr", "recall@5", "recall@10"]
EVAL_DIR = Path(__file__).resolve().parent.parent  # .../RAG Eval

# Folder tài liệu chung (đa cây) — khớp mọi cây khi lọc theo cây.
GENERAL_CROPS = {"pdf", "chung", "tong-hop", "tổng hợp"}


def target_crop(qrels: metrics.Qrels, qid: str) -> str | None:
    """Cây mục tiêu của câu = cây của tài liệu đúng (nhãn cao nhất) trong qrels."""
    rels = qrels.get(qid, {})
    if not rels:
        return None
    exact = max(rels.items(), key=lambda kv: kv[1])[0]
    return exact.split("/", 1)[0]


def _crop_ok(chunk, crop: str, source_lookup: dict[str, str]) -> bool:
    """Chunk có thuộc cây mục tiêu không (folder chung/đa cây luôn khớp)."""
    doc = map_chunk_to_doc(chunk, source_lookup)
    if not doc:
        return False
    c = doc.split("/", 1)[0]
    return c in GENERAL_CROPS or c == crop


# Đọc dữ liệu

def load_queries(path: Path) -> list[dict[str, str]]:
    # utf-8-sig: tự bỏ BOM nếu có (Excel hay thêm), vẫn đọc được file không BOM
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_qrels(path: Path) -> metrics.Qrels:
    qrels: metrics.Qrels = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            qid = row["query_id"]
            qrels.setdefault(qid, {})[row["doc_id"]] = int(row["relevance"])
    return qrels


# Chạy retrieval

async def evaluate_config(
    config,
    in_scope: list[dict[str, str]],
    oos: list[dict[str, str]],
    source_lookup: dict[str, str],
    qrels: metrics.Qrels,
    crop_filter: bool,
) -> tuple[metrics.Run, list[float]]:
    """Chạy 1 cấu hình trên toàn bộ câu hỏi.

    Khi crop_filter=True: truyền cây mục tiêu cho retriever VÀ hậu-lọc chunk theo
    cây (đồng nhất cho mọi cấu hình → mô phỏng bối cảnh đã biết cây từ model ảnh).

    Returns:
        (run, oos_top_scores) — run cho câu in-scope; điểm top-1 cho câu OOS.
    """
    run: metrics.Run = {}
    for q in in_scope:
        qid = q["query_id"]
        crop = target_crop(qrels, qid) if crop_filter else None
        chunks = await config.retrieve(q["question"], crop)
        if crop_filter and crop:
            chunks = [c for c in chunks if _crop_ok(c, crop, source_lookup)]
        ranked = rank_documents(chunks, source_lookup)
        run[qid] = {doc: 1.0 / (i + 1) for i, doc in enumerate(ranked)}

    oos_top_scores: list[float] = []
    for q in oos:
        chunks = await config.retrieve(q["question"], None)  # OOS: không lọc cây
        oos_top_scores.append(max((c.score for c in chunks), default=0.0))

    return run, oos_top_scores


async def run_real(args, queries, qrels):
    """Chế độ thật: gọi retriever rag-engine."""
    print("Đang nạp thư viện (torch/transformers)", flush=True)
    from retrievers import build_bundle, build_configs

    print("Đang khởi tạo retriever (load embedder + reranker, dựng BM25 từ Qdrant)…",
          flush=True)
    bundle = build_bundle(
        depth=args.depth,
        qdrant_host=args.qdrant_host,
        qdrant_port=args.qdrant_port,
        reranker_model=args.reranker_model,
    )
    print(f"  Sẵn sàng | BM25 corpus = {len(bundle.bm25)} chunk"
          + (" | LỌC THEO CÂY: bật" if args.crop_filter else ""))

    alphas = [float(a) for a in args.alphas.split(",") if a.strip()]
    names = [n.strip() for n in args.configs.split(",")] if args.configs else None
    configs = build_configs(bundle, alphas=alphas, depth=args.depth, names=names)

    in_scope = [q for q in queries if q["type"] == "in_scope"]
    oos = [q for q in queries if q["type"] == "out_of_scope"]

    runs: dict[str, metrics.Run] = {}
    oos_scores: dict[str, list[float]] = {}
    score_kinds: dict[str, str] = {}
    for cfg in configs:
        print(f"  → chạy cấu hình '{cfg.name}'…")
        run, oos_top = await evaluate_config(
            cfg, in_scope, oos, bundle.source_lookup, qrels, args.crop_filter
        )
        runs[cfg.name] = run
        oos_scores[cfg.name] = oos_top
        score_kinds[cfg.name] = cfg.score_kind

    return runs, oos_scores, score_kinds, in_scope, oos


# Chế độ soát nhãn: in chunk thật retriever trả về

async def dump_retrieved(args, queries, qrels):
    """Xuất top-k chunk thật cho từng câu (kèm nhãn hiện có) để soát relevance.

    Công cụ KIỂM CHỨNG NỘI DUNG: đọc đoạn văn retriever thật sự lấy về và so với
    nhãn trong qrels — chỗ nào lệch thực tế thì sửa nhãn cho đúng.
    """
    print("Đang nạp thư viện (torch/transformers)…", flush=True)
    from retrievers import build_bundle, build_configs
    from doc_mapping import map_chunk_to_doc

    bundle = build_bundle(
        depth=args.depth, qdrant_host=args.qdrant_host, qdrant_port=args.qdrant_port
    )
    alphas = [float(a) for a in args.alphas.split(",") if a.strip()]
    names = [n.strip() for n in args.configs.split(",")] if args.configs else ["hybrid@0.7"]
    configs = build_configs(bundle, alphas=alphas, depth=args.depth, names=names)
    if not configs:
        configs = build_configs(bundle, alphas=[0.7], depth=args.depth, names=["hybrid@0.7"])
    cfg = configs[0]
    topk = args.dump_topk
    print(f"  Soát nhãn bằng cấu hình '{cfg.name}', top-{topk} chunk mỗi câu…", flush=True)

    lines = [
        f"# Soát nhãn — top-{topk} chunk retriever trả về",
        "",
        f"Cấu hình truy xuất: **{cfg.name}**. Cột `nhãn` = relevance hiện có trong "
        "qrels cho cặp (câu, tài liệu) đó (`—` = chưa gán ⇒ coi như 0). "
        "Đọc trích đoạn và sửa nhãn trong `data/qrels.csv` nếu thấy lệch thực tế.",
    ]
    for q in queries:
        chunks = await cfg.retrieve(q["question"])
        labels = qrels.get(q["query_id"], {})
        lines += [
            "",
            f"## {q['query_id']} [{q['type']}] — {q['question']}",
            "",
            "| # | doc_id | nhãn | score | nguồn | trích đoạn |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for i, c in enumerate(chunks[:topk], 1):
            doc = map_chunk_to_doc(c, bundle.source_lookup) or "?"
            label = labels.get(doc, "—")
            src = (c.source or "").replace("\\", "/").split("/")[-1]
            snip = (c.text or "").replace("\n", " ").replace("|", "/")[:160]
            lines.append(f"| {i} | {doc} | {label} | {c.score:.3f} | {src} | {snip} |")

    out = args.results_dir / "retrieved_dump.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Đã ghi bản soát nhãn vào: {out}")


# Chế độ self-test (không cần Qdrant/torch)

def _pseudo_rand(seed: str) -> float:
    """Số giả ngẫu nhiên tất định trong [0,1) từ chuỗi seed."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def run_self_test(queries, qrels):
    """Sinh run GIẢ LẬP để kiểm thử metrics/Wilcoxon/IO mà không cần retriever.

    Mỗi 'cấu hình' xếp tài liệu theo relevance thật + nhiễu khác nhau, nên NDCG
    chênh nhau giữa các cấu hình (đủ để kiểm tra Wilcoxon ra số).
    """
    in_scope = [q for q in queries if q["type"] == "in_scope"]
    oos = [q for q in queries if q["type"] == "out_of_scope"]
    fake_configs = {"dense": 0.9, "bm25": 0.5, "hybrid@0.7": 1.3, "hybrid@0.7+rerank": 1.8}

    runs: dict[str, metrics.Run] = {}
    oos_scores: dict[str, list[float]] = {}
    score_kinds: dict[str, str] = {}
    for name, strength in fake_configs.items():
        run: metrics.Run = {}
        for q in in_scope:
            qid = q["query_id"]
            scored = []
            for doc, rel in qrels.get(qid, {}).items():
                noise = _pseudo_rand(f"{name}:{qid}:{doc}")
                scored.append((rel * strength + noise, doc))
            scored.sort(reverse=True)
            run[qid] = {doc: 1.0 / (i + 1) for i, (_, doc) in enumerate(scored)}
        runs[name] = run
        oos_scores[name] = [_pseudo_rand(f"{name}:oos:{q['query_id']}") * 0.6 for q in oos]
        score_kinds[name] = "synthetic"

    return runs, oos_scores, score_kinds, in_scope, oos


# ── Trình bày & lưu kết quả ──────────────────────────────────────────────────

def md_table(headers: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join([line, sep, body])


def compute_all(runs, oos_scores, in_scope, oos, qrels, oos_threshold):
    """Tính chỉ số xếp hạng (NDCG/MRR/Recall), false-trigger, Wilcoxon."""
    inscope_qrels = {q["query_id"]: qrels[q["query_id"]] for q in in_scope if q["query_id"] in qrels}

    means: dict[str, dict[str, float]] = {}
    per_query: dict[str, dict[str, dict[str, float]]] = {}
    for name, run in runs.items():
        m, pq = metrics.evaluate_metrics(inscope_qrels, run, METRIC_NAMES)
        means[name] = m
        per_query[name] = pq

    ft: dict[str, float] = {
        name: metrics.false_trigger_rate(scores, oos_threshold)
        for name, scores in oos_scores.items()
    }

    # Wilcoxon trên NDCG@5 (chỉ các cặp mà cả 2 cấu hình tồn tại)
    qids = [q["query_id"] for q in in_scope if q["query_id"] in qrels]
    candidate_pairs = [
        ("hybrid@0.7", "dense"),
        ("hybrid@0.7+rerank", "hybrid@0.7"),
        ("hybrid@0.7", "bm25"),
    ]
    wilcoxon_rows = []
    for a, b in candidate_pairs:
        if a in per_query and b in per_query:
            va = [per_query[a]["ndcg@5"][q] for q in qids]
            vb = [per_query[b]["ndcg@5"][q] for q in qids]
            stat, p, sig = metrics.wilcoxon_test(va, vb)
            wilcoxon_rows.append((a, b, stat, p, sig))

    return means, ft, wilcoxon_rows


def save_and_print(means, ft, wilcoxon_rows, score_kinds, n_in, n_oos,
                   oos_threshold, backend, results_dir, is_self_test, crop_filter):
    results_dir.mkdir(parents=True, exist_ok=True)

    # Bảng chỉ số xếp hạng (NDCG + MRR + Recall)
    m_headers = ["config", "NDCG@3", "NDCG@5", "NDCG@10", "MRR", "Recall@5", "Recall@10"]
    m_rows = [
        [name,
         f'{m["ndcg@3"]:.4f}', f'{m["ndcg@5"]:.4f}', f'{m["ndcg@10"]:.4f}',
         f'{m["mrr"]:.4f}', f'{m["recall@5"]:.4f}', f'{m["recall@10"]:.4f}']
        for name, m in means.items()
    ]
    with (results_dir / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(m_headers)
        w.writerows(m_rows)

    # False trigger
    ft_headers = ["config", "score_kind", "false_trigger_rate"]
    ft_rows = [[name, score_kinds[name], f"{rate:.3f}"] for name, rate in ft.items()]
    with (results_dir / "false_trigger.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(ft_headers)
        w.writerows(ft_rows)

    # Wilcoxon
    wx_headers = ["config_A", "config_B", "statistic", "p_value", "significant(p<0.05)"]
    wx_rows = [
        [a, b, f"{stat:.4f}", f"{p:.4g}", "CÓ" if sig else "không"]
        for a, b, stat, p, sig in wilcoxon_rows
    ]
    with (results_dir / "wilcoxon.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(wx_headers)
        w.writerows(wx_rows)

    crop_note = "BẬT (đã biết cây)" if crop_filter else "tắt (cold, toàn corpus)"

    # In màn hình
    print("\n" + "=" * 64)
    print(f"KẾT QUẢ ĐÁNH GIÁ RETRIEVAL  (backend: {backend})")
    print(f"in-scope: {n_in} | out-of-scope: {n_oos} | ngưỡng OOS: {oos_threshold} | lọc cây: {crop_note}")
    print("=" * 64)
    print("\n[Chỉ số xếp hạng — câu in-scope]")
    print(md_table(m_headers, m_rows))
    print("\n[False trigger — câu out-of-scope]")
    print(md_table(ft_headers, ft_rows))
    print("\n[Wilcoxon signed-rank trên NDCG@5]")
    print(md_table(wx_headers, wx_rows) if wx_rows else "  (không đủ cặp cấu hình)")

    # report.md
    warn = ""
    if is_self_test:
        warn = ("> ⚠️ **CHẾ ĐỘ SELF-TEST**: số liệu dưới đây sinh từ run GIẢ LẬP để "
                "kiểm thử pipeline, KHÔNG phải kết quả retrieval thật.\n\n")
    report = f"""# Báo cáo đánh giá Retrieval — VietCropDoctor

{warn}- Backend chỉ số: `{backend}`
- Số câu in-scope: {n_in} | out-of-scope: {n_oos}
- Lọc theo cây (crop filter): **{crop_note}**
- Ngưỡng false-trigger (OOS): {oos_threshold}

> ⚠️ Nhãn relevance gán theo luật taxonomy (có thể soát thêm bằng nội dung —
> xem `results/retrieved_dump.md`). NDCG/MRR/Recall đo chất lượng xếp hạng;
> càng cao càng tốt.

## 1. Chỉ số xếp hạng (câu in-scope)

{md_table(m_headers, m_rows)}

- **NDCG@k**: xếp tài liệu liên quan lên đầu tốt cỡ nào (có tính mức độ liên quan).
- **MRR**: vị trí trung bình của tài liệu liên quan ĐẦU TIÊN (đo độ chính xác top đầu — vai trò của rerank).
- **Recall@k**: bắt được bao nhiêu phần tài liệu liên quan trong top k (điểm mạnh của hybrid).

## 2. False trigger rate (câu out-of-scope)

Tỉ lệ câu lạc chủ đề mà retriever vẫn trả về kết quả có điểm ≥ ngưỡng
({oos_threshold}). Ngưỡng này hiệu chỉnh cho điểm **cosine** (dense/hybrid);
điểm BM25 (raw) và RRF ở thang khác nên cột này với các cấu hình đó chỉ tham khảo.

{md_table(ft_headers, ft_rows)}

## 3. Kiểm định ý nghĩa thống kê (Wilcoxon signed-rank, NDCG@5)

{md_table(wx_headers, wx_rows) if wx_rows else "_(không đủ cặp cấu hình để kiểm định)_"}

p < 0.05 ⇒ khác biệt giữa hai cấu hình có ý nghĩa thống kê trên {n_in} câu in-scope.
"""
    (results_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"\nĐã lưu kết quả vào: {results_dir}")


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Đánh giá retrieval VietCropDoctor")
    p.add_argument("--data-dir", type=Path, default=EVAL_DIR / "data")
    p.add_argument("--results-dir", type=Path, default=EVAL_DIR / "results")
    p.add_argument("--alphas", default="0.5,0.7,0.9", help="alpha quét cho hybrid")
    p.add_argument("--depth", type=int, default=30, help="số chunk lấy mỗi câu")
    p.add_argument("--oos-threshold", type=float, default=0.30)
    p.add_argument("--qdrant-host", default=None,
                   help="ghi đè host Qdrant (dùng 'localhost' khi chạy trên host)")
    p.add_argument("--qdrant-port", type=int, default=None, help="ghi đè port Qdrant")
    p.add_argument("--configs", default=None, help="lọc tập cấu hình (phân tách bởi dấu phẩy)")
    p.add_argument("--crop-filter", action="store_true",
                   help="lọc theo cây mục tiêu (mô phỏng bối cảnh đã biết cây từ model ảnh)")
    p.add_argument("--reranker-model", default=None,
                   help="ghi đè model rerank, vd BAAI/bge-reranker-v2-m3")
    p.add_argument("--self-test", action="store_true",
                   help="kiểm thử pipeline bằng run giả lập (không cần Qdrant/torch)")
    p.add_argument("--dump-retrieved", action="store_true",
                   help="xuất top-k chunk thật cho từng câu (để soát nhãn), không chấm điểm")
    p.add_argument("--dump-topk", type=int, default=10, help="số chunk in mỗi câu khi dump")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # tránh lỗi cp1252 trên Windows
    except Exception:
        pass

    queries = load_queries(args.data_dir / "queries.csv")
    qrels = load_qrels(args.data_dir / "qrels.csv")

    # Chế độ soát nhãn: chỉ xuất chunk, không cần backend NDCG
    if args.dump_retrieved:
        try:
            asyncio.run(dump_retrieved(args, queries, qrels))
        except RuntimeError as exc:
            print(f"\nLỖI MÔI TRƯỜNG: {exc}", file=sys.stderr)
            return 3
        return 0

    try:
        backend = metrics.ndcg_backend_name()
    except ModuleNotFoundError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    try:
        if args.self_test:
            print("== CHẾ ĐỘ SELF-TEST (run giả lập) ==")
            runs, oos_scores, score_kinds, in_scope, oos = run_self_test(queries, qrels)
        else:
            runs, oos_scores, score_kinds, in_scope, oos = asyncio.run(
                run_real(args, queries, qrels)
            )
    except RuntimeError as exc:
        print(f"\nLỖI MÔI TRƯỜNG: {exc}", file=sys.stderr)
        return 3

    means, ft, wilcoxon_rows = compute_all(
        runs, oos_scores, in_scope, oos, qrels, args.oos_threshold
    )
    save_and_print(
        means, ft, wilcoxon_rows, score_kinds, len(in_scope), len(oos),
        args.oos_threshold, backend, args.results_dir, args.self_test, args.crop_filter,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
