"""Dependencias FastAPI (acceso al estado de la aplicación)."""

from __future__ import annotations

from fastapi import Request

from .config import Settings
from .engine import AnalysisEngine, EngineSelection
from .services.analysis import AnalysisService
from .services.monitoring import Monitoring
from .services.store import Store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_engine(request: Request) -> AnalysisEngine:
    return request.app.state.engine


def get_engine_selection(request: Request) -> EngineSelection:
    return request.app.state.selection


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis


def get_monitoring(request: Request) -> Monitoring:
    return request.app.state.monitoring
