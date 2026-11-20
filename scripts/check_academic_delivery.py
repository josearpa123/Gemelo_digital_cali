"""Verify PDF/DOCX delivery, author names and the evidence archive."""

import argparse
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import fitz

AUTHORS = "Milton Alberto Quintero Estrada; Jose David Arias Pantoja"


def prepare(folder):
    docx = folder / "Informe_Gemelo_Digital_Cali.docx"
    with zipfile.ZipFile(docx) as package:
        assert package.testzip() is None
        parts = {name: package.read(name) for name in package.namelist()}
    main = ET.fromstring(parts["word/document.xml"])
    texts = " ".join(main.itertext())
    for author in AUTHORS.split("; "):
        assert author in texts
    assert "[[PAGEBREAK]]" not in texts and "{{" not in texts
    assert "66,5 %" in texts and "18,92" in texts
    assert len([name for name in parts if name.startswith("word/media/")]) >= 4
    quality = {"docx": {"status": "passed", "authors": AUTHORS}}
    for name in ("Informe_Gemelo_Digital_Cali.pdf", "Word_Layout_Inspection.pdf"):
        with fitz.open(folder / name) as document:
            pages = [page.get_text() for page in document]
            text = "\n".join(pages)
            assert all(author in text for author in AUTHORS.split("; "))
            assert "66,5 %" in text and "18,92" in text and "[[PAGEBREAK]]" not in text
            assert all(len(page.strip()) > 80 for page in pages)
            clipped = []
            for i, page in enumerate(document):
                for block in page.get_text("blocks"):
                    if block[0] < -1 or block[2] > page.rect.width + 1:
                        clipped.append(i + 1)
            assert not clipped, clipped
            quality[name] = {"status": "passed", "pages": len(document), "clipped_pages": clipped}
            if name.startswith("Word_"):
                preview = folder / "preview_word"
                preview.mkdir(exist_ok=True)
                sheet = fitz.open()
                canvas = sheet.new_page(width=760, height=math.ceil(len(document) / 4) * 280)
                for i in range(len(document)):
                    x, y = i % 4 * 190, i // 4 * 280
                    canvas.show_pdf_page(fitz.Rect(x + 4, y + 4, x + 186, y + 268), document, i)
                    canvas.insert_text((x + 88, y + 277), str(i + 1), fontsize=7)
                canvas.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(preview / "contact-sheet.png")
                document[0].get_pixmap(matrix=fitz.Matrix(1.1, 1.1)).save(preview / "cover.png")
                sheet.close()
    (folder / "delivery-quality.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    readme = (
        "ANEXOS DEL INFORME DEL GEMELO DIGITAL DE MOVILIDAD URBANA EN CALI\n\n"
        f"Autores: {AUTHORS}\n\n"
        "Experimento: cooperation_20261119. Seis entrenamientos completos; 120 corridas\n"
        "de validacion y 45 corridas de prueba final. Semillas finales: 300-304.\n"
        "Los datos son de simulacion con demanda sintetica, no aforos de campo.\n\n"
        "evidence/: CSV, reportes JSON, decision de seleccion y procedencia.\n"
        "figures/: mapa y figuras del informe; incluye score de validacion complementario.\n"
        "Informe_Gemelo_Digital_Cali.html: version local navegable (abrir con figures/ al lado).\n"
        "source/: plantilla y scripts de generacion. La version Word se formateo y verifico\n"
        "con Microsoft Word; el PDF se genero y reviso por pagina con Chromium/PyMuPDF.\n\n"
        "No se incluyen credenciales, pesos de modelos ni trazas privadas.\n"
    )
    archive = folder / "Anexos_Informe_Gemelo_Digital_Cali.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("LEEME.txt", readme)
        for directory in ("evidence", "figures"):
            for file in sorted((folder / directory).rglob("*")):
                if file.is_file():
                    package.write(file, file.relative_to(folder).as_posix())
        for name in (
            "Informe_Gemelo_Digital_Cali.html",
            "build-info.json",
            "delivery-quality.json",
        ):
            package.write(folder / name, name)
        for name in (
            "academic_report.html",
            "build_academic_report.py",
            "render_academic_report.py",
            "format_academic_word.ps1",
            "check_academic_delivery.py",
        ):
            package.write(Path("scripts") / name, "source/" + name)
    print(json.dumps(quality, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    prepare(parser.parse_args().folder)
