"""
Prompt engineering for the agricultural RAG system.

Design goals:
  1. Ground answers strictly in retrieved context (anti-hallucination).
  2. Cite source documents naturally.
  3. Detect "don't know" cases and respond gracefully.
  4. Keep the system prompt concise to save token budget.
"""
from __future__ import annotations

from rag.models.responses import RetrievedChunk

# System prompt

_SYSTEM_PROMPT = """\
Bạn là trợ lý nông nghiệp của VietCropDoctor, hỗ trợ nông dân Việt Nam nhận biết và xử lý bệnh cây trồng.

NGUYÊN TẮC BẮT BUỘC:
1. CHỈ trả lời dựa trên thông tin có trong [NGỮ CẢNH]. TUYỆT ĐỐI không dùng kiến thức bên ngoài, không suy đoán, không khái quát hoá.
2. KHÔNG tự thêm tên thuốc, hoạt chất, liều lượng, tên khoa học, nguyên nhân hay triệu chứng nếu [NGỮ CẢNH] không ghi. Chỉ nêu tên thuốc/hoạt chất KHI ngữ cảnh có nêu đúng tên đó.
3. KHÔNG thêm lời khuyên phòng ngừa hay xử lý chung chung nếu ngữ cảnh không đề cập. Trả lời ngắn gọn, đúng những gì ngữ cảnh có.
4. Nếu [NGỮ CẢNH] nói về CÂY hoặc BỆNH KHÁC với câu hỏi, hoặc không đủ thông tin để trả lời, hãy NÓI THẲNG là chưa tìm thấy thông tin phù hợp và gợi ý hỏi cụ thể hơn / tham khảo chuyên gia. TUYỆT ĐỐI không trả lời thay bằng cây hay bệnh khác.
5. Trả lời bằng tiếng Việt, thân thiện và dễ hiểu.
6. Cuối câu trả lời, thêm một dòng "Nguồn tham khảo:" liệt kê các tên nguồn (phần "Nguồn:" trong [NGỮ CẢNH]) của những tài liệu bạn đã dùng. Nếu ngữ cảnh không ghi nguồn thì bỏ qua dòng này."""


# Public API

def build_system_prompt() -> str:
    """Return the static system prompt."""
    return _SYSTEM_PROMPT


def build_user_message(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Construct the user turn for the LLM.

    Format::

        [LỊCH SỬ HỘI THOẠI]
        ...

        [NGỮ CẢNH]
        [1] <source>: <text>
        ...

        [CÂU HỎI]
        <question>

    Args:
        question: Sanitised user question.
        chunks:   Reranked retrieved chunks.
        history:  Previous (question, answer) pairs — most recent last.

    Returns:
        Formatted string ready to be sent as the user message.
    """
    parts: list[str] = []

    # Conversation history (max 3 turns to limit context size)
    if history:
        recent = history[-3:]
        history_lines = "\n".join(
            f"Người dùng: {turn['question']}\nTrợ lý: {turn['answer']}"
            for turn in recent
        )
        parts.append(f"[LỊCH SỬ HỘI THOẠI]\n{history_lines}\n")

    # Retrieved context
    if chunks:
        ctx_lines = "\n\n".join(
            f"[{i + 1}] (Nguồn: {_source_label(c)})\n{c.text}"
            for i, c in enumerate(chunks)
        )
        parts.append(f"[NGỮ CẢNH]\n{ctx_lines}")
    else:
        parts.append("[NGỮ CẢNH]\nKhông có thông tin liên quan.")

    # Question
    parts.append(f"[CÂU HỎI]\n{question}")

    return "\n\n".join(parts)


def format_no_context_answer() -> str:
    """Standard fallback when no relevant context is retrieved."""
    return (
        "Tôi chưa tìm thấy thông tin phù hợp trong cơ sở kiến thức. "
        "Bạn có thể hỏi cụ thể hơn về triệu chứng, nguyên nhân hoặc cách phòng trị không?"
    )


# Helpers

def _source_label(chunk: RetrievedChunk) -> str:
    """Human-readable source for a chunk.

    Prefer the curated ``source_name`` from sources.json; fall back to the
    last two path segments of the file path when no source name is set.
    """
    name = (chunk.metadata or {}).get("source_name")
    if name:
        return str(name)
    return _short_source(chunk.source)


def _short_source(source: str) -> str:
    """Return the two last path segments of a source path."""
    parts = source.replace("\\", "/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else source
