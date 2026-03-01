from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class ExperimentState(TypedDict):
    # Set at init — never mutated
    experiment_name: str

    # Written by Node 1
    procedure_steps: list[str]

    # Written by Node 2
    clip_s3_keys: list[str]
    final_video_key: Optional[str]

    # Written by Node 3
    video_url: Optional[str]

    # Set by any node on failure; causes graph to short-circuit to END
    error: Optional[str]
