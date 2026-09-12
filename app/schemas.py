"""Request models shared by all transport endpoints."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ProcessOptions(BaseModel):
    """Transform parameters applied to a single image.

    The same model is reused by the single-file and batch endpoints, so a batch
    run applies identical options to every uploaded file.
    """

    width: Optional[int] = Field(
        default=None, ge=1, le=10000, description="Target width in pixels"
    )
    height: Optional[int] = Field(
        default=None, ge=1, le=10000, description="Target height in pixels"
    )
    mode: Literal["fit", "cover", "crop"] = "fit"
    format: Literal["jpeg", "webp", "png", "original"] = "original"
    quality: int = Field(default=82, ge=1, le=100)

    @model_validator(mode="after")
    def _require_dimensions_for_crop(self) -> "ProcessOptions":
        if self.mode in {"cover", "crop"} and (
            self.width is None or self.height is None
        ):
            raise ValueError(f"mode '{self.mode}' requires both width and height")
        return self
