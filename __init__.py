"""
EchoMind Memory Skill — Hermes Plugin

AI Persistent memory system: 6 memory types + RL self-optimization + Self-Reflective Agent

as MemoryProvider: set memory.provider: echomind in config.yaml
as Plugin: run hermes plugins enable echomind
"""
from .core._reflective_version import get_echomind_version

__version__ = get_echomind_version()

from adapters.hermes_provider import EchomindMemoryProvider

__all__ = ["EchomindMemoryProvider", "__version__"]