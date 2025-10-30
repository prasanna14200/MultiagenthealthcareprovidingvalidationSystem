# src/agents/qa_agent.py
from src.agents.base_agent import BaseAgent

class QAAgent(BaseAgent):
    def __init__(self, name="qa_agent"):
        """
        Quality Assurance Agent
        Performs quality checks after validation phase.
        Accepts 'name' argument to align with orchestrator.
        """
        super().__init__(name)

    async def run(self, payload):
        """
        Performs QA (Quality Assurance) on validated provider data.
        Checks confidence, phone validity, and name match to assign flags and status.
        """
        score = payload.get("score", 0.0)
        matches = payload.get("matches", {})

        flags = []

        # Check low confidence score
        if score < 0.5:
            flags.append("low_confidence")

        # Check phone validity
        if matches.get("phone_valid") is False:
            flags.append("invalid_phone")

        # Check name similarity
        if matches.get("name_score", 0.0) < 0.6:
            flags.append("name_mismatch")

        # Determine QA status
        status = "manual_review" if flags else "confirmed"

        # Return structured QA result
        return {
            "id": payload.get("id"),
            "confidence": round(score, 3),
            "flags": flags,
            "status": status,
        }
