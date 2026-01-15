# tests/test_agents.py
import pytest

@pytest.fixture
def sample_provider():
    return {
        "id": 123,
        "name": "Dr Test",
        "phone": "123-456-7890",
        "email": "doc@example.com",
        "address": "100 Main St",
        "specialty": "Cardiology",
    }


@pytest.mark.asyncio
async def test_validation_agent_success(monkeypatch, sample_provider):
    from src.agents.validation_agent import ValidationAgent

    # Patch external utility functions used inside ValidationAgent
    from src import utils

    monkeypatch.setattr(utils, "normalize_phone", lambda p: "+911234567890")
    monkeypatch.setattr(utils, "fuzzy_ratio", lambda a, b: 0.9)

    agent = ValidationAgent()

    # Call the async run method
    result = await agent.run(sample_provider)

    assert "score" in result
    assert isinstance(result["score"], float)
    assert "matches" in result
    assert "phone_valid" in result["matches"]


@pytest.mark.asyncio
async def test_validation_agent_handles_missing_fields(monkeypatch):
    from src.agents.validation_agent import ValidationAgent
    from src import utils

    monkeypatch.setattr(utils, "normalize_phone", lambda p: None)
    monkeypatch.setattr(utils, "fuzzy_ratio", lambda a, b: 0.5)

    payload = {"id": 99, "name": "NoPhone"}
    agent = ValidationAgent()

    result = await agent.run(payload)

    assert "score" in result
    assert result["matches"]["phone_valid"] is False
