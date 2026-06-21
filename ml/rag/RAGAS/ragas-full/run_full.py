"""RAGAS FULL — đánh giá toàn diện chất lượng RAG (4 chỉ số).

Cần đáp án mẫu (`reference`) trong questions.csv vì 2 chỉ số context cần nó.

  - faithfulness       : LLM có bịa không (câu trả lời dựa trên contexts).
  - answer_relevancy   : câu trả lời có đúng trọng tâm câu hỏi.
  - context_precision  : các chunk LIÊN QUAN có được xếp lên trên không.
  - context_recall     : contexts có CHỨA đủ thông tin của đáp án mẫu không
                         (đo chất lượng RETRIEVAL so với đáp án).

Chạy (host, đã bật Qdrant + Ollama):
    python run_full.py --qdrant-host localhost
    python run_full.py --qdrant-host localhost --llm-model qwen2.5:3b
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.build_dataset import build_dataset, load_jsonl, load_questions, save_jsonl
from common.local_models import get_ragas_embeddings, get_ragas_llm

HERE = Path(__file__).resolve().parent


def main() -> int:
    p = argparse.ArgumentParser(description="RAGAS full")
    p.add_argument("--qdrant-host", default=None, help="dùng 'localhost' khi chạy trên host")
    p.add_argument("--llm-model", default=None, help="model sinh + chấm (vd qwen2.5:3b cho nhanh)")
    p.add_argument("--rebuild", action="store_true", help="chạy lại pipeline thay vì dùng cache")
    args = p.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    cache = HERE / "results" / "dataset.jsonl"
    if cache.exists() and not args.rebuild:
        print(f"Dùng dataset cache: {cache.name} (thêm --rebuild để chạy lại pipeline)")
        samples = load_jsonl(cache)
    else:
        questions = load_questions(HERE / "data" / "questions.csv")
        missing = [q["question"] for q in questions if not (q.get("reference") or "").strip()]
        if missing:
            print(f"⚠️ {len(missing)} câu THIẾU cột 'reference' — context_recall/precision sẽ kém chính xác.")
        print(f"Chạy pipeline RAG cho {len(questions)} câu (cần Qdrant + Ollama)…")
        samples = build_dataset(questions, qdrant_host=args.qdrant_host, llm_model=args.llm_model)
        save_jsonl(samples, cache)

    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import (answer_relevancy, context_precision,
                               context_recall, faithfulness)
    from ragas.run_config import RunConfig

    judge_model = args.llm_model or "settings.llm_model (mặc định)"
    llm = get_ragas_llm(model=args.llm_model)
    emb = get_ragas_embeddings()
    dataset = EvaluationDataset.from_list(samples)

    print("Đang chấm RAGAS bằng LLM-judge local (Qwen) — có thể chậm…", flush=True)
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=emb,
        # timeout cao + 1 worker: full có 4 chỉ số LLM, 7b rất chậm; 2 worker
        # tranh 1 Ollama gây TimeoutError (đã trải nghiệm ở faithfulness).
        run_config=RunConfig(timeout=600, max_workers=1),
    )

    df = result.to_pandas()
    out = HERE / "results"
    df.to_csv(out / "full_scores.csv", index=False, encoding="utf-8-sig")

    cols = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    n_total = len(samples)
    means = {c: float(df[c].mean()) for c in cols if c in df.columns}
    valid = {c: int(df[c].notna().sum()) for c in cols if c in df.columns}
    any_timeout = any(valid[c] < n_total for c in valid)

    print("\n" + "=" * 56)
    print("RAGAS FULL")
    print(f"  Giám khảo (judge): {judge_model}")
    print(f"  Số câu: {n_total}")
    for c in cols:
        if c in means:
            print(f"  {c:<20}: {means[c]:.3f}   (chấm xong {valid[c]}/{n_total})")
    if any_timeout:
        print("  ⚠️ Có câu bị timeout (NaN) — trung bình KHÔNG tính trên đủ số câu.")
    print("=" * 56)

    lines = "\n".join(
        f"- **{c}** = {means[c]:.3f} (chấm xong {valid[c]}/{n_total})"
        for c in cols if c in means
    )
    (out / "report.md").write_text(
        "# RAGAS Full — đánh giá toàn diện RAG\n\n"
        f"- Giám khảo (LLM-judge): `{judge_model}`\n"
        f"- Số câu: {n_total}\n\n"
        f"{lines}\n\n"
        + ("> ⚠️ Một số câu timeout (NaN) → trung bình chưa tính trên đủ số câu; cần chạy lại.\n\n"
           if any_timeout else "")
        + "Ý nghĩa: faithfulness=không bịa · answer_relevancy=đúng trọng tâm · "
        "context_precision=chunk liên quan xếp trên · context_recall=contexts đủ "
        "thông tin so với đáp án mẫu. Tất cả thang 0→1, càng cao càng tốt.\n\n"
        "Điểm từng câu: `results/full_scores.csv`.\n",
        encoding="utf-8",
    )
    print(f"Đã lưu kết quả vào: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
