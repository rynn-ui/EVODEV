"""Agent connectors package: Base interfaces, unified contract, manager, and adapters."""

from evodev.connectors.base import BaseAgentConnector
from evodev.connectors.contract import (
    AgentConnector,
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorIdentity,
    ContextRequest,
    ContextResponse,
    EventIngestResponse,
    HealthStatus,
    OutcomeReport,
    OutcomeResponse,
    RetrievedLessonSnippet,
    UnsupportedCapabilityError,
)
from evodev.connectors.gemini import GeminiCLIConnector
from evodev.connectors.generic import GenericAdapter
from evodev.connectors.hermes import HermesConnector
from evodev.connectors.kilocode import KiloCodeConnector
from evodev.connectors.manager import ConnectorManager, ConnectorRegistry
from evodev.connectors.opencode import OpenCodeConnector
from evodev.connectors.simulation import SimulationAgent

__all__ = [
    "AgentConnector",
    "BaseAgentConnector",
    "ConnectorCapabilities",
    "ConnectorHealth",
    "ConnectorIdentity",
    "ConnectorManager",
    "ConnectorRegistry",
    "ContextRequest",
    "ContextResponse",
    "EventIngestResponse",
    "GeminiCLIConnector",
    "GenericAdapter",
    "HealthStatus",
    "HermesConnector",
    "KiloCodeConnector",
    "OpenCodeConnector",
    "OutcomeReport",
    "OutcomeResponse",
    "RetrievedLessonSnippet",
    "SimulationAgent",
    "UnsupportedCapabilityError",
]
