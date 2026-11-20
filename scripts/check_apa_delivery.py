"""Inspect Word-generated APA deliverables without modifying their packages."""

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import fitz

p = Path("outputs/report_apa_20261119")
base = p / "Informe_Gemelo_Digital_Cali_APA"
ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
with ZipFile(base.with_suffix(".docx")) as z:
    root = ET.fromstring(z.read("word/document.xml"))
    text = "\n".join("".join(e.itertext()) for e in root.findall(".//w:t", ns))
    assert "Milton Alberto Quintero Estrada" in text
    assert "Jose David Arias Pantoja" in text
    assert "[[INSTITUTIONAL_COVER]]" not in text and "[[PAGEBREAK]]" not in text
    sections = root.findall(".//w:sectPr", ns)
    margins = [e.find("w:pgMar", ns).attrib for e in sections]
    for margin in margins:
        for side in ("top", "bottom", "left", "right"):
            assert margin[f"{{{ns['w']}}}{side}"] == "1440", margin
    headers = [n for n in z.namelist() if n.startswith("word/header") and n.endswith(".xml")]
    assert any(b"PAGE" in z.read(h) for h in headers)

with fitz.open(base.with_suffix(".pdf")) as doc:
    texts = [page.get_text() for page in doc]
    (p / "extracted-text.txt").write_text(
        "\n\n".join(f"PAGE {i + 1}\n{t}" for i, t in enumerate(texts)), encoding="utf-8"
    )
    all_text = "\n".join(texts)
    assert all(len(t.strip()) > 80 for t in texts), [len(t) for t in texts]
    assert "Milton Alberto Quintero Estrada" in texts[0]
    assert "Jose David Arias Pantoja" in texts[0]
    assert "Universidad Cooperativa de Colombia" in texts[0]
    assert "ENTORNOS IoT" not in all_text
    assert "66,5 %" in all_text and "18,92" in all_text
    assert "[[" not in all_text
    clipping = []
    for i, page in enumerate(doc):
        assert tuple(page.rect) == (0, 0, 612, 792)
        for b in page.get_text("blocks"):
            if b[0] < -1 or b[2] > 613:
                clipping.append((i + 1, b[:4]))
    assert not clipping, clipping
    preview = p / "preview"
    preview.mkdir(exist_ok=True)
    doc[0].get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(preview / "cover.png")
    sheet = fitz.open()
    overview = sheet.new_page(width=760, height=math.ceil(len(doc) / 4) * 270)
    for i in range(len(doc)):
        x, y = (i % 4) * 190, (i // 4) * 270
        overview.show_pdf_page(fitz.Rect(x + 4, y + 4, x + 186, y + 255), doc, i)
        overview.insert_text((x + 90, y + 266), str(i + 1), fontsize=7)
    overview.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(preview / "contact-sheet.png")
    (p / "extracted-text.txt").write_text(
        "\n\n".join(f"PAGE {i + 1}\n{t}" for i, t in enumerate(texts)), encoding="utf-8"
    )
    quality = {
        "status": "passed",
        "pages": len(doc),
        "text_lengths": [len(t) for t in texts],
        "authors_verified": True,
        "letter_size": True,
        "margins_inches": 1,
        "clipped_blocks": clipping,
    }
    (p / "apa-quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps(quality))
