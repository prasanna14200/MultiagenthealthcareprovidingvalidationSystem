# src/agents/base_agent.py
import abc
from typing import Dict, Any

class BaseAgent(abc.ABC):
    def __init__(self, name: str, llm_client=None):
        self.name = name
        self.llm_client = llm_client

    @abc.abstractmethod
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass
