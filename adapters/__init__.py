# EchoMind platform adapters
#
# NOTE: the HTTP app is imported LAZILY. Loading EchoMind as a Hermes memory
# provider must not import FastAPI — nor construct the module-level global
# MainMemoryAgent in http_api — into the gateway process. Under Hermes v0.23.1
# multiplexing (#140058) a provider instance must stay profile-local; the eager
# `app` import was pure module-level side effect. `from adapters import app`
# still works via __getattr__.
from .hermes_provider import EchomindMemoryProvider

__all__ = ["EchomindMemoryProvider", "app"]


def register(ctx):
    """Hermes v0.20+ memory-provider discovery entry point.

    v0.20 loads memory providers directly from __init__.py via
    load_memory_provider(), looking for a register() function or a
    MemoryProvider subclass.  The legacy plugin.yaml `hermes.register`
    path is no longer used by the memory loader.
    """
    ctx.register_memory_provider(EchomindMemoryProvider())


def __getattr__(name):
    if name == "app":
        from .http_api import app as _app
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")