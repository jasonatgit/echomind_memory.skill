# EchoMind platform adapters
from .hermes_provider import EchomindMemoryProvider
from .http_api import app

__all__ = ["EchomindMemoryProvider", "app"]


def register(ctx):
    """Hermes v0.20+ memory-provider discovery entry point.

    v0.20 loads memory providers directly from __init__.py via
    load_memory_provider(), looking for a register() function or a
    MemoryProvider subclass.  The legacy plugin.yaml `hermes.register`
    path is no longer used by the memory loader.
    """
    ctx.register_memory_provider(EchomindMemoryProvider())