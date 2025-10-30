# src/agents/reconciliation_agent.py
from .base_agent import BaseAgent
from ..utils import fuzzy_ratio



class ReconciliationAgent(BaseAgent):
    async def run(self, payload):
        # payload: {"validation_result":..., "enrichment":..., "ocr":...}
        final_profile = {}
        sources = ["validation", "enrichment", "ocr"]

        # Example: reconcile name
        names = [payload.get("validation_result", {}).get("name"),
                 payload.get("enrichment", {}).get("education"),  # optional
                 payload.get("ocr", {}).get("name")]
        # pick most frequent / highest confidence name (mocked)
        final_name = max(set(filter(None, names)), key=names.count, default=None)
        final_profile["name"] = {"value": final_name, "confidence": 0.95, "sources": sources}

        # Similarly for phone, address, specialty
        # Compute final_confidence
        final_profile["final_confidence"] = 0.9
        final_profile["flags"] = []  # e.g., ["low_confidence_phone"] if <0.5

        return {"id": payload["id"], "profile": final_profile}
