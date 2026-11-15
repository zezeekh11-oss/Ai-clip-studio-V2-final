from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Settings(BaseModel):
    language: Literal["auto", "id", "en"] = "auto"
    whisper_model: Literal["tiny", "base"] = "base"
    mode: Literal["adaptive", "professional"] = "adaptive"
    clip_count: int = Field(3, ge=1, le=10)
    min_duration: int = Field(20, ge=10, le=90)
    max_duration: int = Field(60, ge=15, le=180)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    resolution: Literal["720p", "1080p"] = "720p"
    subtitles: bool = True

    @model_validator(mode="after")
    def check_range(self):
        if self.min_duration >= self.max_duration:
            raise ValueError("Durasi minimum harus lebih kecil dari durasi maksimum.")
        return self


class RenderRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=20)
