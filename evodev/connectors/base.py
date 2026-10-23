"""Abstract base connector interface for AI coding agent integrations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseAgentConnector(ABC):
    """Generic interface for bridging external coding agents into EvoDev."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the connector display identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the target host environment or agent binary is installed and reachable."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health and configuration state."""
        pass

    @abstractmethod
    def start(self) -> None:
        """Initialize and activate the connector."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Gracefully terminate connector background processes."""
        pass

    @abstractmethod
    def assemble_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> str:
        """Retrieve relevant experience and format into an agent-ready advisory snippet."""
        pass
