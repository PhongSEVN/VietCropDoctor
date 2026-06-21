"""RAGAS — KIỂM TRA LLM CÓ BỊA KHÔNG (faithfulness + answer relevancy).

Câu hỏi đặt ra: sau khi retriever đã trả các chunk về, LLM có bịa thông tin
không có trong chunk hay không?

Chỉ cần (câu hỏi, câu trả lời, contexts) — KHÔNG cần đáp án mẫu:
  - faithfulness:      tỉ lệ "khẳng định" trong câu trả lời được CHỨNG MINH bởi
                       contexts. = 1.0 ⇒ không bịa; < 1.0 ⇒ có câu LLM tự nghĩ ra.
  - answer_relevancy:  câu trả lời có đúng trọng tâm câu hỏi không.

Chạy (host, đã bật Qdrant + Ollama):
    python run_faithfulness.py --qdrant-host localhost
    python run_faithfulness.py --qdrant-host localhost --llm-model qwen2.5:3b   # nhanh hơn
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Cho phép import gói `common` ở thư mục RAGAS/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.build_dataset import build_dataset, load_jsonl, load_questions, save_jsonl
from common.local_models import get_ragas_embeddings, get_ragas_llm

HERE = Path(__file__).resolve().parent


def main() -> int:
    p = argparse.ArgumentParser(description="RAGAS faithfulness / chống bịa")
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
        print(f"Chạy pipeline RAG cho {len(questions)} câu (cần Qdrant + Ollama)…")
        samples = build_dataset(questions, qdrant_host=args.qdrant_host, llm_model=args.llm_model)
        save_jsonl(samples, cache)

    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import answer_relevancy, faithfulness
    from ragas.run_config import RunConfig

    judge_model = args.llm_model or "settings.llm_model (mặc định)"
    llm = get_ragas_llm(model=args.llm_model)
    emb = get_ragas_embeddings()
    dataset = EvaluationDataset.from_list(samples)

    print("Đang chấm RAGAS bằng LLM-judge local (Qwen) — có thể chậm…", flush=True)
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=llm,
        embeddings=emb,
        # timeout cao + 1 worker: giám khảo 7b làm faithfulness (tách + verify
        # từng khẳng định) rất chậm; 2 worker tranh 1 Ollama gây TimeoutError.
        run_config=RunConfig(timeout=600, max_workers=1),
    )

    df = result.to_pandas()
    out = HERE / "results"
    df.to_csv(out / "faithfulness_scores.csv", index=False, encoding="utf-8-sig")

    f_mean = float(df["faithfulness"].mean())
    a_mean = float(df["answer_relevancy"].mean())
    n_total = len(samples)
    f_valid = int(df["faithfulness"].notna().sum())
    a_valid = int(df["answer_relevancy"].notna().sum())
    print("\n" + "=" * 56)
    print("RAGAS — FAITHFULNESS (chống bịa)")
    print(f"  Giám khảo (judge)   : {judge_model}")
    print(f"  Số câu              : {n_total}")
    print(f"  faithfulness        : {f_mean:.3f}   (chấm xong {f_valid}/{n_total}; 1.0 = không bịa)")
    print(f"  answer_relevancy    : {a_mean:.3f}   (chấm xong {a_valid}/{n_total})")
    if f_valid < n_total or a_valid < n_total:
        print("  ⚠️ Có câu bị timeout (NaN) — trung bình KHÔNG tính trên đủ số câu.")
    print("=" * 56)

    (out / "report.md").write_text(
        "# RAGAS — Faithfulness (kiểm tra LLM có bịa không)\n\n"
        f"- Giám khảo (LLM-judge): `{judge_model}`\n"
        f"- Số câu: {n_total}\n"
        f"- **faithfulness = {f_mean:.3f}** (chấm xong {f_valid}/{n_total}) — tỉ lệ khẳng định "
        "trong câu trả lời được chứng minh bởi chunk lấy về. **1.0 = LLM không bịa**; càng "
        "thấp càng nhiều thông tin LLM tự nghĩ ra (không có trong tài liệu).\n"
        f"- **answer_relevancy = {a_mean:.3f}** (chấm xong {a_valid}/{n_total}) — câu trả lời "
        "có đúng trọng tâm câu hỏi không.\n"
        + ("- ⚠️ Một số câu timeout (NaN) → trung bình KHÔNG tính trên đủ số câu; cần chạy lại.\n"
           if (f_valid < n_total or a_valid < n_total) else "")
        + "\n"
        "Điểm từng câu: `results/faithfulness_scores.csv`.\n",
        encoding="utf-8",
    )
    print(f"Đã lưu kết quả vào: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
