"""Profiles package: .vxp format packaging, unpackaging, and lifecycle manager."""

from evodev.profiles.format import ProfileArchiveFormat
from evodev.profiles.inspector import ProfileInspector
from evodev.profiles.manager import ProfileManager

__all__ = ["ProfileArchiveFormat", "ProfileInspector", "ProfileManager"]

