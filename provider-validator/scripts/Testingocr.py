from pdf2image import convert_from_path
import pytesseract
import re


import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"E:\tesse\tesseract.exe"
pdf_path = "data/scanned_pdfs/sample_1.pdf"

# Convert PDF to images
pages = convert_from_path(pdf_path, dpi=200, poppler_path=r"D:\Downloads\Release-25.12.0-0\poppler-25.12.0\Library\bin")

# Extract text from first page
text = pytesseract.image_to_string(pages[0])
print("OCR Text Preview:\n", text[:500])



def extract_provider_fields(text):
    name = None
    m = re.search(r'Name[:\s]+([A-Z][a-z]+\s[A-Z][a-z]+)', text)
    if m: name = m.group(1)
    
    phone = None
    m2 = re.search(r'Phone[:\s]+([0-9\-\+\s\(\)]+)', text)
    if m2: phone = m2.group(1)
    
    addr = None
    m3 = re.search(r'Address[:\s]+(.+)', text)
    if m3: addr = m3.group(1).strip()
    
    return {"name": name, "phone": phone, "address": addr}

fields = extract_provider_fields(text)
print(fields)

