# src/reports/pdf_generator.py
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def create_report(providers):
    """Generate a PDF report of validated providers."""
    os.makedirs("data/reports", exist_ok=True)
    pdf_path = "data/reports/provider_report.pdf"

    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(200, 750, "Provider Validation Report")

    c.setFont("Helvetica", 11)
    y = 720
    for p in providers:
        line = f"ID: {p.get('id', 'N/A')} | Name: {p.get('name', 'Unknown')} | Specialty: {p.get('specialty', 'N/A')}"
        c.drawString(50, y, line)
        y -= 15
        if y < 50:
            c.showPage()
            y = 750

    c.save()
    return pdf_path
