"""Pipeline package unifying resume ingestion, discovery, matching, verification, and persistence."""

from backend.pipeline.orchestrator import JobIntelligencePipeline
from backend.pipeline.schemas import (
    PipelineConfig,
    PipelineJobOutput,
    PipelineRunSummary,
    PipelineStageMetrics,
)

__all__ = [
    "JobIntelligencePipeline",
    "PipelineConfig",
    "PipelineJobOutput",
    "PipelineRunSummary",
    "PipelineStageMetrics",
]
