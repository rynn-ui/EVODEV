"""Agent connectors package: Base interfaces, simulation, OpenCode, and Gemini CLI."""

from evodev.connectors.base import BaseAgentConnector
from evodev.connectors.simulation import SimulationAgent

__all__ = ["BaseAgentConnector", "SimulationAgent"]
