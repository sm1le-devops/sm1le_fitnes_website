import logging
from pathlib import Path

from fpdf import FPDF

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_PATH = BASE_DIR / "static" / "fonts" / "DejaVuSans.ttf"


def create_pdf_buffer(plan_text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    if FONT_PATH.exists():
        pdf.add_font("DejaVu", "", str(FONT_PATH), unicode=True)
        pdf.set_font("DejaVu", "", 12)
    else:
        logging.error("Шрифт не найден: %s", FONT_PATH)
        pdf.set_font("Arial", size=12)

    clean_text = (
        str(plan_text)
        .replace("**", "")
        .replace("__", "")
        .replace("#", "")
    )

    for line in clean_text.split("\n"):
        line = line.strip()

        if line:
            pdf.multi_cell(0, 10, txt=line)
        else:
            pdf.ln(5)

    try:
        pdf_output = pdf.output()

        return bytes(pdf_output)

    except Exception:
        logging.exception("Ошибка при создании PDF")
        raise