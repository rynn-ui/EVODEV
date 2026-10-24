"""Lifecycle management for EvoDev (initialization, migrations, uninstallation)."""

from evodev.lifecycle.uninstaller import (
    EvoDevUninstaller,
    InstallationType,
    UninstallPlan,
    UninstallPlanItem,
    UninstallResult,
)

__all__ = [
    "EvoDevUninstaller",
    "InstallationType",
    "UninstallPlan",
    "UninstallPlanItem",
    "UninstallResult",
]
