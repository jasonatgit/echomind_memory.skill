"""EchoMind Memory Skill — Hermes Plugin
AI Persistent memory system: 6 memory types + RL self-optimization + Self-Reflective Agent

as MemoryProvider: set memory.provider: echomind in config.yaml
as Plugin: run hermes plugins enable echomind
"""
import os, sys
# Hermes plugin loader creates this module as _hermes_user_memory.echomind
# with spec_from_file_location — Python has no package context, so relative
# imports fail.  Add plugin dir to sys.path so absolute imports work.
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from core._reflective_version import get_echomind_version

__version__ = get_echomind_version()

from adapters.hermes_provider import EchomindMemoryProvider

__all__ = ["EchomindMemoryProvider", "__version__"]