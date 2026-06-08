# validation/__init__.py
# ────────────────────────────────────────────────────────────────
from .result import ValidationResult
from .validators import (
    IValidator, 
    HarvestValidator, 
    ProcessingValidator, 
    RoastingValidator, 
    DistributionValidator, 
    RetailValidator, 
    NullValidator
)

def get_validator(event_type: str) -> IValidator:
    """
    Factory Method: Khởi tạo và trả về đối tượng validator phù hợp
    dựa trên loại sự kiện (event_type).
    """
    if event_type == "HARVEST":
        return HarvestValidator()
    elif event_type == "PROCESSING":
        return ProcessingValidator()
    elif event_type == "ROASTING":
        return RoastingValidator()
    elif event_type == "DISTRIBUTION":
        return DistributionValidator()
    elif event_type == "RETAIL":
        return RetailValidator()
    else:
        # Áp dụng Null Object Pattern cho các sự kiện chưa cấu hình logic
        return NullValidator()
