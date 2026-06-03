# validation/result.py
# ────────────────────────────────────────────────────────────────

class ValidationResult:
    def __init__(self, is_valid: bool = True, errors: list = None, warnings: list = None, trust_score: float = 100.0):
        self.is_valid = is_valid
        self.errors = errors if errors is not None else []
        self.warnings = warnings if warnings is not None else []
        self.trust_score = trust_score

    def add_error(self, error: str):
        """Thêm lỗi chặn đứng (Error). Làm dữ liệu không hợp lệ."""
        self.is_valid = False
        self.errors.append(error)
        # Giảm đáng kể điểm tin cậy nếu có lỗi
        self.trust_score = max(0.0, self.trust_score - 25.0)

    def add_warning(self, warning: str):
        """Thêm cảnh báo (Warning). Không chặn ghi nhận nhưng giảm điểm tin cậy."""
        self.warnings.append(warning)
        # Giảm nhẹ điểm tin cậy cho mỗi cảnh báo
        self.trust_score = max(0.0, self.trust_score - 10.0)

    def to_dict(self) -> dict:
        """Chuyển đổi đối tượng thành dictionary để dễ dàng trả về dạng JSON."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "trust_score": round(self.trust_score, 1)
        }
