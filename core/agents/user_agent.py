# EchoMind — User Memory Agent

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from ..models.user import UserMemory

logger = logging.getLogger("MemoryAgent")


class UserMemoryAgent:
    def __init__(self):
        self.store: Dict[str, UserMemory] = {}
        self.cache: Dict[str, UserMemory] = {}

    def get(self, user_id: str, platform: str = None) -> Dict[str, Any]:
        if user_id in self.cache:
            mem = self.cache[user_id]
            return self._extract_platform_prefs(mem, platform)
        if user_id not in self.store:
            self.store[user_id] = UserMemory(user_id=user_id)
        mem = self.store[user_id]
        self.cache[user_id] = mem
        return self._extract_platform_prefs(mem, platform)

    def _extract_platform_prefs(self, mem: UserMemory, platform: str) -> Dict[str, Any]:
        """Extract current platform preferences from platform-aware preferences JSON."""
        raw = mem.dict()
        prefs = raw.get("preferences", {})
        if isinstance(prefs, dict) and "_default" in prefs:
            # v3.0+ platform-aware format
            merged = dict(prefs.get("_default", {}))
            if platform and platform in prefs:
                merged.update(prefs.get(platform, {}))
            raw["preferences"] = merged
        # else: pre-v3.0 Legacy format, return directly
        return raw

    def update(self, user_id: str, key: str, value: Any,
               source: str = "implicit", platform: str = None) -> bool:
        if user_id not in self.store:
            self.store[user_id] = UserMemory(user_id=user_id)
        mem = self.store[user_id]
        if key in ["preferences", "habits"]:
            if isinstance(value, dict):
                getattr(mem, key).update(value)
            else:
                logger.warning("update(%s) expects dict, got %s", key, type(value).__name__)
                return False
        elif key == "history":
            mem.history.append({"timestamp": datetime.now(timezone.utc).isoformat(), "action": value})
        else:
            setattr(mem, key, value)
        mem.version += 1
        mem.last_updated = datetime.now(timezone.utc)
        self.cache[user_id] = mem
        return True