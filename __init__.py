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

# ── Startup confirmation (user-visible, for Hermes plugin load) ──
try:
    from core.storage.sqlite_store import SqliteStore
    db = SqliteStore()
    db.connect()
    db.ensure_tables()
    row_count = db._conn.execute("SELECT count(*) FROM user_memory").fetchone()[0]
    print(f"🧠 EchoMind v{__version__} — 记忆存储正常 ({row_count} 条用户记忆)")
except Exception as e:
    print(f"⚠️  EchoMind v{__version__} — 记忆存储异常: {e}")