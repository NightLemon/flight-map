"""Flight Map 共享数据契约。"""

from .airac import AiracPeriod, airac_period_at
from .models import (
    Coverage,
    DatasetRelease,
    LicenseStatus,
    QualityStatus,
    RawAsset,
    Source,
    SourceProduct,
    ValidationIssue,
)
from .registry import load_sources

__all__ = [
    "AiracPeriod",
    "Coverage",
    "DatasetRelease",
    "LicenseStatus",
    "QualityStatus",
    "RawAsset",
    "Source",
    "SourceProduct",
    "ValidationIssue",
    "airac_period_at",
    "load_sources",
]
