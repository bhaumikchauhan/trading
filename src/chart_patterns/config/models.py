from pydantic import BaseModel, Field, model_validator


class ZigZagConfig(BaseModel):
    threshold_pct: float = Field(gt=0)


class SavgolConfig(BaseModel):
    window_length: int = Field(gt=0)
    polyorder: int = Field(ge=0)

    @model_validator(mode="after")
    def check_window_valid(self) -> "SavgolConfig":
        if self.window_length % 2 == 0:
            raise ValueError("window_length must be odd for a Savitzky-Golay filter")
        if self.polyorder >= self.window_length:
            raise ValueError("polyorder must be less than window_length")
        return self


class SmoothingConfig(BaseModel):
    zigzag: ZigZagConfig
    savgol: SavgolConfig


class LoggingConfig(BaseModel):
    level: str = "INFO"

    @model_validator(mode="after")
    def check_level_valid(self) -> "LoggingConfig":
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level.upper() not in valid_levels:
            raise ValueError(f"level must be one of {sorted(valid_levels)}, got {self.level!r}")
        return self


class DoubleTopConfig(BaseModel):
    height_similarity_pct: float = Field(gt=0)
    min_trough_depth_pct: float = Field(gt=0)
    max_time_separation_bars: int = Field(gt=0)
    min_time_separation_bars: int = Field(gt=0)

    @model_validator(mode="after")
    def check_time_separation_order(self) -> "DoubleTopConfig":
        if self.min_time_separation_bars >= self.max_time_separation_bars:
            raise ValueError("min_time_separation_bars must be less than max_time_separation_bars")
        return self


class DoubleBottomConfig(BaseModel):
    depth_similarity_pct: float = Field(gt=0)
    min_peak_prominence_pct: float = Field(gt=0)
    max_time_separation_bars: int = Field(gt=0)
    min_time_separation_bars: int = Field(gt=0)

    @model_validator(mode="after")
    def check_time_separation_order(self) -> "DoubleBottomConfig":
        if self.min_time_separation_bars >= self.max_time_separation_bars:
            raise ValueError("min_time_separation_bars must be less than max_time_separation_bars")
        return self


class HeadAndShouldersConfig(BaseModel):
    shoulder_height_similarity_pct: float = Field(gt=0)
    min_head_prominence_pct: float = Field(gt=0)
    max_neckline_slope_pct: float = Field(gt=0)
    max_time_separation_bars: int = Field(gt=0)
    min_time_separation_bars: int = Field(gt=0)

    @model_validator(mode="after")
    def check_time_separation_order(self) -> "HeadAndShouldersConfig":
        if self.min_time_separation_bars >= self.max_time_separation_bars:
            raise ValueError("min_time_separation_bars must be less than max_time_separation_bars")
        return self
