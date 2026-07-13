"""Read-only UI configuration endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import AppSettings
from .deps import get_app_settings


router = APIRouter(prefix="/config", tags=["config"])


def _load_config(config_dir: Path, name: str) -> dict:
    """Load one public UI config from the canonical config directory."""
    config_path = config_dir / f"{name}.json"
    if not config_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Config not found: {name}",
        )

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load config: {name}",
        ) from exc


@router.get("/fields")
async def get_fields_config(settings: AppSettings = Depends(get_app_settings)) -> dict:
    return _load_config(settings.config_dir, "fields")


@router.get("/products")
async def get_products_config(settings: AppSettings = Depends(get_app_settings)) -> dict:
    return _load_config(settings.config_dir, "products")


@router.get("/regions")
async def get_regions_config(settings: AppSettings = Depends(get_app_settings)) -> dict:
    return _load_config(settings.config_dir, "regions")
