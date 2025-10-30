# scripts/generate_pdfs.py
import pandas as pd
from fpdf import FPDF
import os

df = pd.read_csv("data/providers_sample.csv")

os.makedirs("data/scanned_pdfs", exist_ok=True)

for i, row in df.iterrows():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Name: {row['name']}", ln=True)
    pdf.cell(0, 10, f"Phone: {row['phone']}", ln=True)
    pdf.cell(0, 10, f"Address: {row['address']}", ln=True)
    pdf.cell(0, 10, f"Specialty: {row['specialty']}", ln=True)
    pdf_file = f"data/scanned_pdfs/sample_{i%5 + 1}.pdf"
    pdf.output(pdf_file)
