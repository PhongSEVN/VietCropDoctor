"""Chỉ số đánh giá retrieval: NDCG, MRR, Recall, false-trigger, Wilcoxon.

Các chỉ số xếp hạng KHÔNG tự viết tay — dùng thư viện chuẩn:
  - Ưu tiên `ranx` (ranx.evaluate với "ndcg@k", "mrr", "recall@k").
  - Nếu không có ranx thì fallback `pytrec_eval` (ndcg_cut, recip_rank, recall).
Nếu thiếu cả hai → báo lỗi rõ ràng (không âm thầm dùng công thức nhà làm).
"""
from __future__ import annotations

# qrels: {query_id: {doc_id: relevance(int)}}
# run:   {query_id: {doc_id: score(float)}}
Qrels = dict[str, dict[str, int]]
Run = dict[str, dict[str, float]]


def ndcg_backend_name() -> str:
    """Tên backend khả dụng ('ranx' | 'pytrec_eval'). Lỗi nếu không có."""
    try:
        import ranx  # noqa: F401
        return "ranx"
    except ModuleNotFoundError:
        pass
    try:
        import pytrec_eval  # noqa: F401
        return "pytrec_eval"
    except ModuleNotFoundError:
        pass
    raise ModuleNotFoundError(
        "Cần `ranx` (ưu tiên) hoặc `pytrec_eval` để tính NDCG/MRR/Recall. "
        "Cài: pip install ranx  (hoặc: pip install pytrec_eval)"
    )


# ── Tính chỉ số xếp hạng (ndcg@k | mrr | recall@k) ───────────────────────────

def _eval_ranx(qrels: Qrels, run: Run, metrics: list[str]) -> dict[str, dict[str, float]]:
    from ranx import Qrels as RxQrels, Run as RxRun, evaluate

    per_query: dict[str, dict[str, float]] = {m: {} for m in metrics}
    for qid, rels in qrels.items():
        scores = run.get(qid, {})
        if not scores:
            for m in metrics:
                per_query[m][qid] = 0.0
            continue
        rq = RxQrels.from_dict({qid: {d: int(r) for d, r in rels.items()}})
        rr = RxRun.from_dict({qid: {d: float(s) for d, s in scores.items()}})
        res = evaluate(rq, rr, metrics)
        if len(metrics) == 1:
            res = {metrics[0]: res}
        for m in metrics:
            per_query[m][qid] = float(res[m])
    return per_query


def _pytrec_key(metric: str) -> str:
    """Đổi 'ndcg@5'/'mrr'/'recall@10' sang khoá pytrec_eval."""
    if metric == "mrr":
        return "recip_rank"
    name, k = metric.split("@")
    if name == "ndcg":
        return f"ndcg_cut_{k}"
    if name == "recall":
        return f"recall_{k}"
    raise ValueError(f"Chỉ số không hỗ trợ: {metric}")


def _eval_pytrec(qrels: Qrels, run: Run, metrics: list[str]) -> dict[str, dict[str, float]]:
    import pytrec_eval

    families = set()
    for m in metrics:
        families.add("recip_rank" if m == "mrr" else ("ndcg_cut" if m.startswith("ndcg") else "recall"))

    qrels_int = {q: {d: int(r) for d, r in rels.items()} for q, rels in qrels.items()}
    run_float = {q: {d: float(s) for d, s in run.get(q, {}).items()} for q in qrels_int}
    raw = pytrec_eval.RelevanceEvaluator(qrels_int, families).evaluate(run_float)

    per_query: dict[str, dict[str, float]] = {m: {} for m in metrics}
    for qid in qrels_int:
        q_res = raw.get(qid, {})
        for m in metrics:
            per_query[m][qid] = float(q_res.get(_pytrec_key(m), 0.0))
    return per_query


def evaluate_metrics(
    qrels: Qrels,
    run: Run,
    metrics: list[str],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """Tính các chỉ số xếp hạng.

    Args:
        metrics: vd ["ndcg@3", "ndcg@5", "ndcg@10", "mrr", "recall@5", "recall@10"].

    Returns:
        (mean, per_query) — mean = {metric: trung bình}, per_query = {metric: {qid: giá trị}}.
    """
    backend = ndcg_backend_name()
    per_query = _eval_ranx(qrels, run, metrics) if backend == "ranx" else _eval_pytrec(qrels, run, metrics)
    mean = {
        m: (sum(per_query[m].values()) / len(per_query[m]) if per_query[m] else 0.0)
        for m in metrics
    }
    return mean, per_query


# False trigger (out-of-scope)
def false_trigger_rate(top_scores: list[float], threshold: float) -> float:
    """Tỉ lệ câu out-of-scope mà điểm cao nhất vượt ngưỡng (→ tư vấn sai)."""
    if not top_scores:
        return 0.0
    return sum(1 for s in top_scores if s >= threshold) / len(top_scores)


# Kiểm định Wilcoxon

def wilcoxon_test(a: list[float], b: list[float]) -> tuple[float, float, bool]:
    """Wilcoxon signed-rank giữa 2 vector chỉ số ghép cặp theo query.

    Returns:
        (statistic, p_value, significant) với significant = p < 0.05.
        Nếu mọi hiệu = 0 → trả (nan, 1.0, False).
    """
    from scipy.stats import wilcoxon

    if len(a) != len(b):
        raise ValueError("Hai vector phải cùng độ dài (ghép cặp theo query).")
    if all(abs(x - y) < 1e-12 for x, y in zip(a, b)):
        return float("nan"), 1.0, False
    try:
        stat, p = wilcoxon(a, b)
    except ValueError:
        return float("nan"), 1.0, False
    return float(stat), float(p), bool(p < 0.05)
