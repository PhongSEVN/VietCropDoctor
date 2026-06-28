"""Prompt templates for each stage of the multi-agent reasoning chain."""

SYSTEM_PROMPT = """Bạn là chuyên gia nông nghiệp AI của hệ thống VietCropDoctor, chuyên tư vấn về bệnh cây trồng cho nông dân Việt Nam.

Nhiệm vụ của bạn:
1. Phân tích kết quả chẩn đoán bệnh từ mô hình thị giác máy tính
2. Tổng hợp kiến thức từ cơ sở dữ liệu nông nghiệp
3. Đưa ra khuyến nghị điều trị cụ thể, thực tế và an toàn

Luôn trả lời bằng tiếng Việt. Hãy thực tế và thận trọng — nên đề nghị tham khảo chuyên gia khi độ tin cậy thấp."""

REASONING_PROMPT_TEMPLATE = """
## Kết quả chẩn đoán hình ảnh
- Bệnh phát hiện: {disease}
- Độ tin cậy: {confidence:.1%}
- Mức độ nghiêm trọng: {severity}
- Điểm mức độ: {severity_score:.2f}/1.00
- Lời khuyên ban đầu: {severity_advice}

## Kiến thức từ cơ sở dữ liệu
{knowledge_text}

## Câu hỏi của người dùng (nếu có)
{user_query}

---
Dựa trên thông tin trên, hãy đưa ra phân tích và khuyến nghị theo định dạng sau:

**Tóm tắt**: [1-2 câu tóm tắt tình trạng]

**Hành động ngay**:
- [Hành động cần làm ngay lập tức]
- [Hành động cần làm ngay lập tức]

**Điều trị**:
- [Biện pháp điều trị cụ thể]
- [Biện pháp điều trị cụ thể]

**Phòng ngừa**:
- [Biện pháp phòng ngừa lâu dài]
- [Biện pháp phòng ngừa lâu dài]

**Theo dõi**: [Hướng dẫn theo dõi sau điều trị]
"""


def build_reasoning_prompt(
    disease: str,
    confidence: float,
    severity: str,
    severity_score: float,
    severity_advice: str,
    knowledge_text: str,
    user_query: str | None,
) -> str:
    return REASONING_PROMPT_TEMPLATE.format(
        disease=disease,
        confidence=confidence,
        severity=severity,
        severity_score=severity_score,
        severity_advice=severity_advice,
        knowledge_text=knowledge_text or "Không tìm thấy thông tin liên quan trong cơ sở dữ liệu.",
        user_query=user_query or "Không có câu hỏi cụ thể.",
    )
