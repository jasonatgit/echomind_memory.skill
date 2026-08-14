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
                # A-H1 fix: keep in-memory structure consistent with what's
                # persisted. DB save_user() stores preferences in a platform-aware
                # "_default"-nested format (see sqlite_store._merge_platform_prefs).
                # A flat .update() here would write new keys at the top level of
                # that nested dict, where _extract_platform_prefs() discards them
                # -> newly inferred prefs silently lost. Mirror _merge_platform_prefs
                # so the in-memory dict stays in the same nested shape.
                if key == "preferences" and isinstance(mem.preferences, dict):
                    existing = mem.preferences
                    # Handle legacy flat in-memory store (pre-v3): normalize once
                    if "_default" not in existing:
                        non_default = {k: v for k, v in existing.items()
                                       if k != "_default"}
                        existing = {"_default": non_default} if non_default else {"_default": {}}
                        mem.preferences = existing
                    existing["_default"].update(value)
                    if platform and platform != "_default":
                        existing.setdefault(platform, {}).update(value)
                else:
                    getattr(mem, key).update(value)
            else:
                logger.warning("update(%s) expects dict, got %s", key, type(value).__name__)
                return False
        elif key == "history":
            # V8-8 fix: include platform (and keep the callers that pass
            # project) so rendered activity entries aren't blank; previously
            # only timestamp+action were stored while memory_agent's direct
            # writes carried project/platform — inconsistent rendering.
            entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "action": value}
            if platform:
                entry["platform"] = platform
            mem.history.append(entry)
        else:
            setattr(mem, key, value)
        mem.version += 1
        mem.last_updated = datetime.now(timezone.utc)
        self.cache[store_key] = mem
        return True