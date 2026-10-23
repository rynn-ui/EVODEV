"""Collector package: Event normalization, git tracking, and ingestion."""

from evodev.collector.git_tracker import GitTracker
from evodev.collector.normalizer import EventNormalizer
from evodev.collector.collector_service import CollectorService

__all__ = ["GitTracker", "EventNormalizer", "CollectorService"]
