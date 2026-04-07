"""Pipeline execution engine."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from musinsights.pipeline.stages import Stage, StageResult, StageStatus

console = Console()


@dataclass
class PipelineResult:
    """Result of a complete pipeline execution."""

    stages: list[tuple[str, StageResult[Any]]] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def success(self) -> bool:
        """Check if all stages completed successfully."""
        return all(
            r.status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
            for _, r in self.stages
        )

    @property
    def duration_seconds(self) -> float | None:
        """Total pipeline duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_stage_result(self, name: str) -> StageResult[Any] | None:
        """Get the result of a specific stage by name."""
        for stage_name, result in self.stages:
            if stage_name == name:
                return result
        return None


class PipelineRunner:
    """Orchestrates execution of pipeline stages.

    Supports sequential execution of stages, with optional progress
    tracking and error handling.
    """

    def __init__(self, stages: list[Stage[Any, Any]] | None = None) -> None:
        """Initialize the pipeline runner.

        Args:
            stages: Optional list of stages to execute.
        """
        self.stages: list[Stage[Any, Any]] = stages or []

    def add_stage(self, stage: Stage[Any, Any]) -> "PipelineRunner":
        """Add a stage to the pipeline.

        Args:
            stage: Stage to add.

        Returns:
            Self for chaining.
        """
        self.stages.append(stage)
        return self

    async def run(
        self,
        initial_input: Any = None,
        stop_on_failure: bool = True,
        progress_callback: Callable[[str, StageResult[Any]], None] | None = None,
    ) -> PipelineResult:
        """Execute all stages in sequence.

        Args:
            initial_input: Input for the first stage.
            stop_on_failure: Whether to stop execution on stage failure.
            progress_callback: Optional callback for stage completion.

        Returns:
            PipelineResult with all stage results.
        """
        result = PipelineResult(started_at=datetime.utcnow())
        current_input = initial_input

        for stage in self.stages:
            stage_result = await stage.run(current_input)
            result.stages.append((stage.name, stage_result))

            if progress_callback:
                progress_callback(stage.name, stage_result)

            if stage_result.status == StageStatus.FAILED and stop_on_failure:
                break

            if stage_result.status == StageStatus.COMPLETED:
                current_input = stage_result.output

        result.completed_at = datetime.utcnow()
        return result

    async def run_with_progress(
        self,
        initial_input: Any = None,
        stop_on_failure: bool = True,
    ) -> PipelineResult:
        """Execute pipeline with Rich progress display.

        Args:
            initial_input: Input for the first stage.
            stop_on_failure: Whether to stop on failure.

        Returns:
            PipelineResult with all stage results.
        """
        result = PipelineResult(started_at=datetime.utcnow())
        current_input = initial_input

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            main_task = progress.add_task(
                "Running pipeline...",
                total=len(self.stages),
            )

            for stage in self.stages:
                progress.update(main_task, description=f"[cyan]{stage.name}[/cyan]")

                stage_result = await stage.run(current_input)
                result.stages.append((stage.name, stage_result))

                if stage_result.status == StageStatus.COMPLETED:
                    progress.update(main_task, advance=1)
                    current_input = stage_result.output
                elif stage_result.status == StageStatus.SKIPPED:
                    progress.update(main_task, advance=1)
                else:
                    console.print(f"[red]Stage '{stage.name}' failed: {stage_result.error}[/red]")
                    if stop_on_failure:
                        break

        result.completed_at = datetime.utcnow()
        return result


async def run_parallel_stages(
    stages: list[Stage[Any, Any]],
    inputs: list[Any],
    max_concurrent: int = 4,
) -> list[StageResult[Any]]:
    """Run multiple stage instances in parallel.

    Useful for processing batches of items through the same stage.

    Args:
        stages: Stage instances to run (can be the same stage with different inputs).
        inputs: Input data for each stage.
        max_concurrent: Maximum concurrent executions.

    Returns:
        List of stage results in the same order as inputs.
    """
    if len(stages) != len(inputs):
        raise ValueError("Number of stages must match number of inputs")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(stage: Stage[Any, Any], input_data: Any) -> StageResult[Any]:
        async with semaphore:
            return await stage.run(input_data)

    tasks = [
        run_with_semaphore(stage, input_data)
        for stage, input_data in zip(stages, inputs)
    ]

    return await asyncio.gather(*tasks)
