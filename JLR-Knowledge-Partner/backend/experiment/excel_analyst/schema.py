"""The model can describe structure and references, never replacement cell values."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PictureLink(StrictModel):
    picture_id: str
    target_range: str = Field(description="A1 range of the record or caption associated with this picture")
    evidence_cells: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(max_length=600)


class MappedRegion(StrictModel):
    range: str = Field(description="Inclusive A1 range inside the supplied scope; no sheet prefix")
    kind: Literal["table", "transposed_table", "key_value", "picture_strip", "requirement_list", "text", "frame", "unknown"]
    orientation: Literal["rows", "columns", "none"]
    header_rows: list[int] = Field(max_length=20)
    header_columns: list[int] = Field(max_length=20, description="1-based columns, useful for transposed tables")
    title_cell: str | None
    evidence_cells: list[str] = Field(max_length=30)
    evidence_pictures: list[str] = Field(max_length=30, description="Known picture IDs supporting this region, including picture-only areas")
    evidence_shapes: list[str] = Field(max_length=30, description="Known textbox/chart/shape IDs supporting an object-only area")
    picture_links: list[PictureLink] = Field(max_length=100)
    confidence: float = Field(ge=0, le=1, description="Self-reported confidence, not a calibrated probability")
    needs_review: bool
    reason: str = Field(max_length=1200)


class LayoutProposal(StrictModel):
    regions: list[MappedRegion] = Field(min_length=1, max_length=32)
    unresolved: list[str] = Field(max_length=50, description="Ambiguities, missing evidence, or a need to join adjacent candidates")
