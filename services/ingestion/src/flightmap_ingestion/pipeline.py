"""失败关闭的数据采集状态机。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from flightmap_schema import DatasetRelease, SourceProduct, ValidationIssue
from flightmap_schema.publication import check_publication
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
    completed: dict[str, dict[str, str]] = Field(default_factory=dict)


class PromotionGate:
    """发布前强制执行许可、质量和有效期门禁。"""

    @staticmethod
    def check(
        context: IngestionContext,
        product: SourceProduct,
        *,
        at: datetime | None = None,
        audience: Literal["local", "redistribution"] = "local",
    ) -> None:
        release = context.release
        if release is None:
            raise PipelineError("没有候选发布集")
        if context.product_id != product.id:
            raise PipelineError("Context product identity mismatch")
        try:
            check_publication(
                release, product, source_id=context.source_id, at=at, audience=audience
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        if any(issue.severity in {"error", "fatal"} for issue in context.issues):
            raise PipelineError("存在阻断发布的验证问题")


StageHandler = Callable[[IngestionContext], dict[str, str]]

_REQUIRED_OUTPUT = {
    PipelineStage.DISCOVER: "source_url",
    PipelineStage.ACQUIRE: "sha256",
    PipelineStage.VERIFY: "sha256",
    PipelineStage.PARSE: "parser_version",
    PipelineStage.NORMALIZE: "record_count",
    PipelineStage.VALIDATE: "report_sha256",
    PipelineStage.STAGE: "release_id",
    PipelineStage.PROMOTE: "release_id",
}


class IngestionPipeline:
    def __init__(
        self,
        context: IngestionContext,
        product: SourceProduct,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.context = context
        self.product = product
        self.clock = clock

    def advance(self, target: PipelineStage, handler: StageHandler | None = None) -> None:
        if self.context.stage in {PipelineStage.QUARANTINE, PipelineStage.PROMOTE}:
            raise PipelineError("终态任务不能继续执行")

        current_index = _STAGE_ORDER.index(self.context.stage)
        expected = _STAGE_ORDER[current_index + 1]
        if target is not expected:
            raise PipelineError(f"非法状态转换：{self.context.stage} -> {target}，应为 {expected}")

        try:
            if target is PipelineStage.PROMOTE:
                PromotionGate.check(self.context, self.product, at=self.clock())
            if handler is None:
                raise PipelineError(f"{target} requires a handler and stage output")
            output = handler(self.context)
            if not isinstance(output, dict) or not output.get(_REQUIRED_OUTPUT[target]):
                raise PipelineError(f"{target} missing required output: {_REQUIRED_OUTPUT[target]}")
            if target is PipelineStage.PROMOTE:
                PromotionGate.check(self.context, self.product, at=self.clock())
            self.context.completed[target.value] = output
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
