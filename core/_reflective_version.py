# core/_reflective_version.py — Version detection


__all__ = ["get_echomind_version"]

ECHOMIND_VERSION = "1.1.0"


def get_echomind_version() -> str:
    return ECHOMIND_VERSION


def _engine_available() -> bool:
    try:
        import importlib
        mod = importlib.import_module("core._reflective_core")
        return mod is not None
    except (ImportError, ModuleNotFoundError):
        return False
