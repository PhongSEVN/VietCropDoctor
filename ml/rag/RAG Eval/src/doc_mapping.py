"""Map chunk → tài liệu gốc.

Hệ thống truy xuất ở mức CHUNK nhưng nhãn (qrels) gán ở mức TÀI LIỆU, nên cần
quy mỗi chunk về một doc_id. Quy ước đã chốt: doc_id = "crop/disease_name".

Hai nguồn suy doc_id (ưu tiên theo thứ tự):
  1. metadata của chunk: field `crop` + `disease_name` (dense/hybrid mang sẵn).
  2. đường dẫn `source`: .../knowledge/<crop>/<disease>/<file> — dùng khi chunk
     không kèm metadata (vd nhánh BM25-only chỉ trả id), hoặc để đối chiếu.

Cả hai khớp nhau vì metadata vốn được sinh từ chính cấu trúc thư mục này.
"""
from __future__ import annotations

from typing import Any, Optional

# Folder không gắn với một cây cụ thể (tài liệu chung / pdf tổng hợp).
# Tài liệu ở đây có crop = danh sách nhiều cây → không tạo doc_id "crop/disease".
_GENERAL_FOLDERS = {"pdf", "chung", "tong-hop", "tổng hợp"}


def doc_id_from_metadata(metadata: dict[str, Any] | None) -> Optional[str]:
    """Suy doc_id từ metadata. Trả None nếu không đủ thông tin/đa cây."""
    if not metadata:
        return None
    crop = metadata.get("crop")
    disease = metadata.get("disease_name")
    # crop có thể là list (tài liệu đa cây) → không map về 1 doc_id cụ thể
    if not isinstance(crop, str) or not isinstance(disease, str):
        return None
    if not crop or not disease:
        return None
    return f"{crop}/{disease}"


def doc_id_from_source(source: str | None) -> Optional[str]:
    """Suy doc_id từ đường dẫn file source (.../knowledge/<crop>/<disease>/...)."""
    if not source:
        return None
    parts = [p for p in source.replace("\\", "/").split("/") if p]
    if "knowledge" in parts:
        rest = parts[parts.index("knowledge") + 1:]
    else:
        rest = parts
    # bỏ tên file ở cuối (đoạn có phần mở rộng)
    if rest and "." in rest[-1]:
        rest = rest[:-1]
    if not rest:
        return None
    crop = rest[0]
    if crop.lower() in _GENERAL_FOLDERS:
        # Tài liệu chung: định danh theo folder (không có cặp cây/bệnh)
        return f"{crop}/__chung__"
    disease = rest[1] if len(rest) >= 2 else "__chung__"
    return f"{crop}/{disease}"


def map_chunk_to_doc(
    chunk: Any,
    source_lookup: dict[str, str] | None = None,
) -> Optional[str]:
    """Quy 1 chunk về doc_id.

    Args:
        chunk:          RetrievedChunk (có .metadata, .source, .chunk_id).
        source_lookup:  Bản đồ chunk_id → source, dùng khi chunk.source rỗng
                        (vd chunk dựng từ BM25-only). Có thể None.

    Returns:
        doc_id "crop/disease" hoặc None nếu không xác định được.
    """
    doc_id = doc_id_from_metadata(getattr(chunk, "metadata", None))
    if doc_id:
        return doc_id

    source = getattr(chunk, "source", "") or ""
    if not source and source_lookup is not None:
        source = source_lookup.get(getattr(chunk, "chunk_id", ""), "")
    return doc_id_from_source(source)


def rank_documents(
    chunks: list[Any],
    source_lookup: dict[str, str] | None = None,
) -> list[str]:
    """Tạo danh sách xếp hạng TÀI LIỆU từ danh sách chunk.

    Mỗi tài liệu lấy thứ hạng theo LẦN XUẤT HIỆN ĐẦU TIÊN của nó trong danh sách
    chunk (chunk đầu tiên thuộc tài liệu đó). Bỏ qua chunk không map được doc_id.

    Returns:
        Danh sách doc_id theo thứ tự hạng (phần tử 0 = hạng 1), đã loại trùng.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk in chunks:
        doc_id = map_chunk_to_doc(chunk, source_lookup)
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            ordered.append(doc_id)
    return ordered
