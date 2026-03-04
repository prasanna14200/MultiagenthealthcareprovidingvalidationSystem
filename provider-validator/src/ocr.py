# src/ocr.py
from pdf2image import convert_from_path
import pytesseract
import re


import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"E:\tesse\tesseract.exe"
def pdf_to_text(pdf_path, dpi=200):
    pages = convert_from_path(pdf_path, dpi=dpi, poppler_path=r"D:\Downloads\Release-25.12.0-0\poppler-25.12.0\Library\bin")
    text = ""
    for p in pages:
        text += pytesseract.image_to_string(p)
        text += "\n"
    return text

def extract_provider_fields(text):
    # Initialize variables first
    name = None
    phone = None
    addr = None
    specialty = None

    # ---- Name ----
    m = re.search(r'Name[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)', text)
    if m:
        name = m.group(1).strip()
        name = re.sub(r'\n?Phone.*', '', name).strip()

    # ---- Phone ----
    m2 = re.search(r'Phone[:\s]+([0-9\-\+\sx\(\)\.]+)', text)
    if m2:
        phone = m2.group(1).strip()
        phone = re.sub(r'x\d+', '', phone).strip()  # remove extension

    # ---- Address ----
    m3 = re.search(r'Address[:\s]+(.+?)(?:\n|Specialty:|$)', text, re.S)
    if m3:
        addr = m3.group(1).strip()

    # ---- Specialty ----
    m4 = re.search(r'Specialty[:\s]+([A-Za-z &]+)', text)
    if m4:
        specialty = m4.group(1).strip()

    return {
        "name": name,
        "phone": phone,
        "address": addr,
        "specialty": specialty
    }