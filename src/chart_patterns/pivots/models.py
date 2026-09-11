from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Pivot(BaseModel):
    index: int
    timestamp: datetime
    price: float
    type: Literal["peak", "trough"]
