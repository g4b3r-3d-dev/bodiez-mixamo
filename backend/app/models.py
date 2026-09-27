from __future__ import annotations

from pydantic import BaseModel, Field


class BlenderPathRequest(BaseModel):
    executable_path: str = Field(min_length=1, max_length=4096)


class SettingsResponse(BaseModel):
    blender_path: str | None
    detected_path: str | None


class BlenderTaskResponse(BaseModel):
    task_id: str


class AssetTaskResponse(BaseModel):
    asset_id: str
    task_id: str


class PreparationTaskResponse(BaseModel):
    asset_id: str
    preparation_id: str
    task_id: str
