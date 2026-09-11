from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from ..pivots.models import Pivot


class Candidate(BaseModel):
    pattern_type: str
    pivots: list[Pivot]
    confidence_score: float = Field(ge=0, le=1)
    metrics: dict[str, float] = Field(default_factory=dict)
    symbol: str | None = None
    timeframe: str | None = None

    @model_validator(mode="after")
    def check_pivots_non_empty(self) -> "Candidate":
        if not self.pivots:
            raise ValueError("Candidate must reference at least one pivot")
        return self

    @property
    def start_index(self) -> int:
        return self.pivots[0].index

    @property
    def end_index(self) -> int:
        return self.pivots[-1].index

    @property
    def start_timestamp(self) -> datetime:
        return self.pivots[0].timestamp

    @property
    def end_timestamp(self) -> datetime:
        return self.pivots[-1].timestamp
