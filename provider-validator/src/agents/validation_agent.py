# src/agents/validation_agent.py
import asyncio, aiohttp, json
from .base_agent import BaseAgent
from bs4 import BeautifulSoup
from src.ocr import pdf_to_text, extract_provider_fields
from src.utils import normalize_phone, fuzzy_ratio
import phonenumbers

class ValidationAgent(BaseAgent):
    def __init__(self, name="validation"):
        super().__init__(name)

    async def fetch_website(self, session, url):
        try:
            if not url.startswith("http"):
                url = "http://" + url
            async with session.get(url, timeout=10) as r:
                return await r.text()
        except Exception:
            return ""

    async def run(self, payload):
        # payload: row dict from CSV with keys: id, name, npi, phone, address, website, specialty, scanned_pdf
        result = {"id": payload.get("id"), "sources": {}, "matches": {}}
        # 1) OCR extraction if scanned_pdf exists
        scanned = payload.get("scanned_pdf")
        if scanned:
            try:
                text = pdf_to_text(scanned, dpi=200)
                ocr_fields = extract_provider_fields(text)
                result["sources"]["ocr"] = {"text_preview": text[:800], "fields": ocr_fields}
            except Exception as e:
                result["sources"]["ocr"] = {"error": str(e)}
        # 2) Website scrape
        website = payload.get("website")
        async with aiohttp.ClientSession() as session:
            if website:
                html = await self.fetch_website(session, website)
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    text = soup.get_text(separator="\n")
                    result["sources"]["website"] = {"text_preview": text[:800]}
            # else no website

        # 3) Basic phone normalization & check
        src_phone = payload.get("phone")
        normalized = None
        if src_phone:
            normalized = normalize_phone(src_phone)
            try:
                pn = phonenumbers.parse(src_phone, "US")
                phone_valid = phonenumbers.is_valid_number(pn)
            except:
                phone_valid = False
        else:
            phone_valid = False

        result["matches"]["phone_valid"] = phone_valid
        result["matches"]["phone_normalized"] = normalized

        # 4) simple fuzzy name match: claimed vs ocr (if exists)
        name_claimed = payload.get("name","")
        name_ocr = result.get("sources",{}).get("ocr",{}).get("fields",{}).get("name","")
        name_score = fuzzy_ratio(name_claimed, name_ocr)
        result["matches"]["name_score"] = name_score

        # 5) address fuzzy
        addr_claimed = payload.get("address","")
        addr_ocr = result.get("sources",{}).get("ocr",{}).get("fields",{}).get("address","")
        addr_score = fuzzy_ratio(addr_claimed, addr_ocr)
        result["matches"]["address_score"] = addr_score

        # 6) simple combined score
        phone_score = 1.0 if phone_valid else 0.0
        final_score = 0.4 * name_score + 0.3 * phone_score + 0.3 * addr_score
        result["score"] = final_score

        return result
