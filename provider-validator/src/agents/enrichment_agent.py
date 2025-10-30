# src/agents/enrichment_agent.py
from .base_agent import BaseAgent
import aiohttp

class EnrichmentAgent(BaseAgent):
    async def fetch(self, session, url):
        try:
            async with session.get(url, timeout=10) as r:
                return await r.json()  # API response
        except:
            return {}

    async def run(self, payload):
        # Example: enrich using mocked API
        enrichment = {"education": None, "certifications": [], "hospital_affiliations": []}
        website = payload.get("website")
        async with aiohttp.ClientSession() as session:
            if website:
                # mock enrichment data
                enrichment["education"] = "MD, Cardiology"
                enrichment["certifications"] = ["Board Certified"]
                enrichment["hospital_affiliations"] = ["City Hospital"]
        return {"id": payload["id"], "enrichment": enrichment}
