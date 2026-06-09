# EchoMind — Context Memory Agent

import logging
from typing import List, Dict

from ..models.context import ContextMessage, ContextMemory

logger = logging.getLogger("MemoryAgent")


class ContextMemoryAgent:
    def __init__(self):
        self.memory = ContextMemory()

    def add_message(self, message: Dict[str, str]) -> None:
        msg = ContextMessage(**message)
        self.memory.messages.append(msg)
        if len(self.memory.messages) > self.memory.window_size:
            self.memory.messages.pop(0)

    def get_context(self) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.memory.messages]

    def clear(self) -> None:
        self.memory.messages = []