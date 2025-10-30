# src/ocr.py
from pdf2image import convert_from_path
import pytesseract
import re

def pdf_to_text(pdf_path, dpi=200):
    pages = convert_from_path(pdf_path, dpi=dpi)
    text = ""
    for p in pages:
        text += pytesseract.image_to_string(p)
        text += "\n"
    return text

def extract_provider_fields(text):
    # conservative regex-based extraction
    name = re.sub(r'\n?Phone.*', '', name).strip()
    m = re.search(r'Name[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)', text)
    if m:
        name = m.group(1).strip()

    phone = re.sub(r'x\d+', '', phone).strip()
    m2 = re.search(r'Phone[:\s]+([0-9\-\+\sx\(\)\.]+)', text)
    if m2:
        phone = m2.group(1).strip()
        # strip extensions like x1015
        phone = re.sub(r'x\d+','', phone).strip()

    addr = None
    m3 = re.search(r'Address[:\s]+(.+?)(?:\n|Specialty:|$)', text, re.S)
    if m3:
        addr = m3.group(1).strip()

    specialty = None
    m4 = re.search(r'Specialty[:\s]+([A-Za-z &]+)', text)
    if m4:
        specialty = m4.group(1).strip()

    return {"name": name, "phone": phone, "address": addr, "specialty": specialty}
