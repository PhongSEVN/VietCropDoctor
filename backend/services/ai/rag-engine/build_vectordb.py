"""
rag/build_vectordb.py
Offline script — reads .txt knowledge files, chunks them, embeds via
OpenAI, and upserts into Qdrant.

Run manually:
    python -m rag.build_vectordb

This script is also imported by rag_chain.py for the ``chunk_text``
and ``parse_metadata`` helper functions.
"""

import sys
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = PROJECT_ROOT / "configs" / "rag_config.yaml"

SECTION_KEYWORDS = {
    "triệu_chứng":        ["TRIỆU CHỨNG"],
    "nguyên_nhân":        ["NGUYÊN NHÂN"],
    "điều_kiện":          ["ĐIỀU KIỆN PHÁT SINH"],
    "phòng_trị":          ["PHÒNG TRỊ"],
    "thuốc":              ["THUỐC KHUYẾN NGHỊ"],
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def detect_section(text: str) -> str:
    upper = text.upper()
    for section, markers in SECTION_KEYWORDS.items():
        if any(m in upper for m in markers):
            return section
    return "tổng_quan"


def parse_metadata(txt_path: Path) -> dict:
    text = txt_path.read_text(encoding="utf-8")
    meta = {"class_name": txt_path.stem, "crop": "unknown", "vi_name": txt_path.stem}
    for line in text.splitlines()[:5]:
        if line.startswith("LOẠI CÂY:"):
            crop_vi = line.replace("LOẠI CÂY:", "").strip().lower()
            if "lúa" in crop_vi:
                meta["crop"] = "rice"
            elif "mía" in crop_vi:
                meta["crop"] = "sugarcane"
            elif "cà phê" in crop_vi:
                meta["crop"] = "cafe"
            meta["crop_vi"] = crop_vi
        elif line.startswith("TÊN BỆNH:"):
            meta["vi_name"] = line.replace("TÊN BỆNH:", "").strip()
    return meta


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[dict]:
    lines = text.splitlines()
    chunks: list[dict] = []
    current: list[str] = []
    current_size = 0
    current_section = "tổng_quan"

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Phát hiện section header
        section = detect_section(stripped)
        if section != "tổng_quan" and any(
            stripped.upper().startswith(m)
            for markers in SECTION_KEYWORDS.values()
            for m in markers
        ):
            current_section = section

        current.append(stripped)
        current_size += len(stripped)

        if current_size >= chunk_size:
            chunks.append({
                "text": " ".join(current),
                "section": current_section,
            })
            # Giữ overlap
            overlap_text = " ".join(current)[-overlap:]
            current = [overlap_text] if overlap_text else []
            current_size = len(overlap_text)

    if current:
        chunks.append({
            "text": " ".join(current),
            "section": current_section,
        })
    return chunks


def main():
    cfg = load_config()
    knowledge_dir = PROJECT_ROOT / cfg["knowledge_dir"]
    chunk_size = cfg["chunking"]["chunk_size"]
    overlap = cfg["chunking"]["overlap"]
    collection = cfg["qdrant"]["collection"]

    txt_files = sorted(knowledge_dir.rglob("*.txt"))
    if not txt_files:
        print(f"Không tìm thấy file .txt trong {knowledge_dir} (kể cả subfolder)")
        print("Hãy chạy rag/process_pdfs.py hoặc rag/crawl_knowledge.py trước.")
        return

    print(f"Tìm thấy {len(txt_files)} file knowledge\n")

    all_chunks: list[dict] = []
    for txt_path in txt_files:
        meta = parse_metadata(txt_path)
        text = txt_path.read_text(encoding="utf-8")
        chunks = chunk_text(text, chunk_size, overlap)
        for chunk in chunks:
            all_chunks.append({
                "text": chunk["text"],
                "class_name": meta["class_name"],
                "vi_name": meta["vi_name"],
                "crop": meta["crop"],
                "section": chunk["section"],
            })
        print(f"  {txt_path.name}: {len(chunks)} chunks")

    print(f"\nTổng chunks: {len(all_chunks)}")

    # --- Embed with OpenAI ---
    from rag.embedder import Embedder

    embedder = Embedder(cfg)
    vector_dim = embedder.dimensions
    texts = [c["text"] for c in all_chunks]
    print(f"\nEmbedding {len(texts)} chunks (dim={vector_dim}) via OpenAI ...")
    vectors = embedder.embed_texts(texts)

    # --- Upsert into Qdrant ---
    from rag.retriever import Retriever

    retriever = Retriever(cfg, vector_dim=vector_dim)
    retriever.recreate_collection()
    count = retriever.upsert_chunks(vectors, all_chunks)
    print(f"\n✓ Đã index {count} chunks vào collection '{collection}'")

    # --- Quick sanity test ---
    test_query = "lúa bị đốm nâu trên lá thì điều trị thế nào?"
    print(f"\nTest query: \"{test_query}\"")
    q_vec = embedder.embed_query(test_query)
    results = retriever.search(q_vec, top_k=3)
    print("\nTop-3 chunks retrieved:")
    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] score={r['score']:.4f} | {r['payload']['vi_name']} | section={r['payload']['section']}")
        print(f"      {r['text'][:200]}...")


if __name__ == "__main__":
    main()
