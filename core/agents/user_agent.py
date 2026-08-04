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

    @staticmethod
    def _key(user_id: str, profile: str = "default") -> str:
        return f"{user_id}:{profile}"

    def get(self, user_id: str, platform: str = None, profile: str = "default") -> Dict[str, Any]:
        key = self._key(user_id, profile)
        if key in self.cache:
            mem = self.cache[key]
            return self._extract_platform_prefs(mem, platform)
        if key not in self.store:
            self.store[key] = UserMemory(user_id=user_id, profile=profile)
        mem = self.store[key]
        self.cache[key] = mem
        return self._extract_platform_prefs(mem, platform)

    def _extract_platform_prefs(self, mem: UserMemory, platform: str) -> Dict[str, Any]:
        """Extract current platform preferences from platform-aware preferences JSON."""
        raw = mem.model_dump(mode="json")
        prefs = raw.get("preferences", {})
        if not isinstance(prefs, dict):
            prefs = {}
        if "_default" in prefs:
            # v3.0+ platform-aware format
            merged = dict(prefs.get("_default", {}))
            if platform and platform in prefs:
                merged.update(prefs.get(platform, {}))
            raw["preferences"] = merged
        # else: pre-v3.0 Legacy format, return directly
        return raw

    def replace_history(self, user_id: str, history: list,
                         profile: str = "default") -> bool:
        """Replace entire history list — avoids O(2^n) nesting bug from update()."""
        store_key = self._key(user_id, profile)
        if store_key not in self.store:
            self.store[store_key] = UserMemory(user_id=user_id, profile=profile)
        mem = self.store[store_key]
        mem.history = history
        mem.version += 1
        mem.last_updated = datetime.now(timezone.utc)
        self.cache[store_key] = mem
        return True

    def update(self, user_id: str, key: str, value: Any,
               source: str = "implicit", platform: str = None,
               profile: str = "default") -> bool:
        store_key = self._key(user_id, profile)
        if store_key not in self.store:
            self.store[store_key] = UserMemory(user_id=user_id, profile=profile)
        mem = self.store[store_key]
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
        self.cache[store_key] = mem
        return True