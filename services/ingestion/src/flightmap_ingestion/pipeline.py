"""失败关闭的数据采集状态机。"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from flightmap_schema import DatasetRelease, SourceProduct, ValidationIssue
from pydantic import BaseModel, Field


class PipelineStage(StrEnum):
    INITIAL = "initial"
    DISCOVER = "discover"
    ACQUIRE = "acquire"
    VERIFY = "verify"
    PARSE = "parse"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    STAGE = "stage"
    PROMOTE = "promote"
    QUARANTINE = "quarantine"


_STAGE_ORDER = [
    PipelineStage.INITIAL,
    PipelineStage.DISCOVER,
    PipelineStage.ACQUIRE,
    PipelineStage.VERIFY,
    PipelineStage.PARSE,
    PipelineStage.NORMALIZE,
    PipelineStage.VALIDATE,
    PipelineStage.STAGE,
    PipelineStage.PROMOTE,
]


class PipelineError(RuntimeError):
    """采集过程违反状态或质量门禁。"""


class IngestionContext(BaseModel):
    source_id: str
    product_id: str
    stage: PipelineStage = PipelineStage.INITIAL
    release: DatasetRelease | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class PromotionGate:
    """发布前强制执行许可、质量和有效期门禁。"""

    @staticmethod
    def check(context: IngestionContext, product: SourceProduct) -> None:
        release = context.release
        if release is None:
            raise PipelineError("没有候选发布集")
        if not product.license_status.allows_redistribution:
            raise PipelineError(f"许可状态 {product.license_status} 不允许发布数据")
        if release.license_status != product.license_status:
            raise PipelineError("发布集许可状态与来源注册表不一致")
        if release.quality_status.value != "verified":
            raise PipelineError("只有 verified 发布集可以提升为 current")
        if any(issue.severity in {"error", "fatal"} for issue in context.issues):
            raise PipelineError("存在阻断发布的验证问题")


StageHandler = Callable[[IngestionContext], None]


class IngestionPipeline:
    def __init__(self, context: IngestionContext, product: SourceProduct) -> None:
        self.context = context
        self.product = product

    def advance(self, target: PipelineStage, handler: StageHandler | None = None) -> None:
        if self.context.stage is PipelineStage.QUARANTINE:
            raise PipelineError("隔离任务不能继续执行")

        current_index = _STAGE_ORDER.index(self.context.stage)
        expected = _STAGE_ORDER[current_index + 1]
        if target is not expected:
            raise PipelineError(f"非法状态转换：{self.context.stage} -> {target}，应为 {expected}")

        try:
            if target is PipelineStage.PROMOTE:
                PromotionGate.check(self.context, self.product)
            if handler is not None:
                handler(self.context)
            self.context.stage = target
        except Exception as exc:
            self.context.stage = PipelineStage.QUARANTINE
            self.context.issues.append(
                ValidationIssue(
                    code="pipeline-stage-failed",
                    severity="fatal",
                    message=f"{target} 阶段失败：{exc}",
                )
            )
            if isinstance(exc, PipelineError):
                raise
            raise PipelineError(str(exc)) from exc
