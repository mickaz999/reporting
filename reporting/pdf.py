"""Met le rapport (Markdown simple) en page dans un PDF."""
import re
from pathlib import Path

from fpdf import FPDF

FONTS = Path("/usr/share/fonts/truetype/dejavu")
ORANGE, DARK, GREY = (255, 106, 0), (28, 26, 23), (138, 128, 121)
# Les emojis ne sont pas dans la police : on les retire
EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿️]")


def _clean(s):
    return EMOJI.sub("", s.replace("**", "").replace("__", "")).strip()


def build_pdf(title, markdown):
    pdf = FPDF()
    if (FONTS / "DejaVuSans.ttf").exists():
        pdf.add_font("body", "", str(FONTS / "DejaVuSans.ttf"))
        pdf.add_font("body", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
        font, enc = "body", lambda s: s
    else:  # police intégrée : uniquement les caractères latins
        font, enc = "helvetica", lambda s: s.encode("latin-1", "replace").decode("latin-1")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(18, 18)
    pdf.add_page()

    pdf.set_font(font, "B", 10)
    pdf.set_text_color(*ORANGE)
    pdf.cell(0, 6, enc("MICKAZ9 GAMING · REPORTING"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, "B", 22)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(0, 10, enc(_clean(title)), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ORANGE)
    pdf.set_line_width(0.8)
    pdf.line(18, pdf.get_y() + 2, 60, pdf.get_y() + 2)
    pdf.ln(6)

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or re.fullmatch(r"[-*_]{3,}", line):
            pdf.ln(2)
            continue
        url = re.fullmatch(r"<?(https?://\S+?)>?", line)
        if url:
            pdf.set_font(font, "", 9)
            pdf.set_text_color(*GREY)
            pdf.cell(6)
            pdf.cell(0, 5, url[1], link=url[1], new_x="LMARGIN", new_y="NEXT")
            continue
        heading = re.match(r"^(#+)\s+(.*)", line)
        if heading:
            big = len(heading[1]) == 1
            pdf.ln(4 if big else 2)
            pdf.set_font(font, "B", 15 if big else 12)
            pdf.set_text_color(*(ORANGE if big else DARK))
            pdf.multi_cell(0, 8 if big else 7, enc(_clean(heading[2])), new_x="LMARGIN", new_y="NEXT")
            continue
        bullet = re.match(r"^([-*•]|\d+[.)])\s+(.*)", line)
        pdf.set_font(font, "", 10.5)
        pdf.set_text_color(*DARK)
        if bullet:
            mark = bullet[1] if bullet[1][0].isdigit() else "•"
            pdf.cell(6, 6, enc(mark))
            pdf.multi_cell(0, 6, enc(_clean(bullet[2])), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 6, enc(_clean(line.lstrip("> "))), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
