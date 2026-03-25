"""Pipeline stage definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class StageStatus(Enum):
    """Status of a pipeline stage execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult(Generic[OutputT]):
    """Result of a stage execution."""

    status: StageStatus
    output: OutputT | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @classmethod
    def success(cls, output: OutputT, **metadata: Any) -> "StageResult[OutputT]":
        """Create a successful result."""
        return cls(
            status=StageStatus.COMPLETED,
            output=output,
            completed_at=datetime.utcnow(),
            metadata=metadata,
        )

    @classmethod
    def failure(cls, error: str, **metadata: Any) -> "StageResult[OutputT]":
        """Create a failed result."""
        return cls(
            status=StageStatus.FAILED,
            error=error,
            completed_at=datetime.utcnow(),
            metadata=metadata,
        )

    @classmethod
    def skipped(cls, reason: str) -> "StageResult[OutputT]":
        """Create a skipped result."""
        return cls(
            status=StageStatus.SKIPPED,
            metadata={"skip_reason": reason},
        )


class Stage(ABC, Generic[InputT, OutputT]):
    """Abstract base class for pipeline stages.

    A stage represents a single step in a data processing pipeline.
    Stages can be composed together using the PipelineRunner.
    """

    name: str = "unnamed_stage"
    description: str = ""

    @abstractmethod
    async def execute(self, input_data: InputT) -> StageResult[OutputT]:
        """Execute the stage with the given input.

        Args:
            input_data: Input data from the previous stage.

        Returns:
            StageResult containing the output or error.
        """
        pass

    def should_skip(self, input_data: InputT) -> str | None:
        """Check if this stage should be skipped.

        Override this method to implement conditional execution.

        Args:
            input_data: Input data that would be processed.

        Returns:
            Skip reason if the stage should be skipped, None otherwise.
        """
        return None

    async def run(self, input_data: InputT) -> StageResult[OutputT]:
        """Run the stage, handling skipping and timing.

        Args:
            input_data: Input data from the previous stage.

        Returns:
            StageResult with timing information.
        """
        # Check if should skip
        if skip_reason := self.should_skip(input_data):
            return StageResult.skipped(skip_reason)

        # Execute with timing
        started_at = datetime.utcnow()
        result = await self.execute(input_data)
        result.started_at = started_at

        if result.completed_at is None:
            result.completed_at = datetime.utcnow()

        return result
