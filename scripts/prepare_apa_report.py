"""Adapt the verified manuscript to APA 7 citations, references and captions."""

import re
import shutil
from pathlib import Path

SOURCE = Path("outputs/report_20261119")
OUTPUT = Path("outputs/report_apa_20261119")

REFERENCES = Path(__file__).with_name("apa_references.html").read_text(encoding="utf-8")

CSS = """
@page { size: Letter; margin: 25.4mm; }
body { font: 12pt 'Times New Roman', serif; line-height: 2; color: black; }
p { margin: 0; text-align: left; text-indent: 12.7mm; }
h1,h2,h3 { font-size: 12pt; font-weight: bold; margin: 0; break-after: avoid; }
h1 { text-align: center; } h2 { text-align: left; } h3 { font-style: italic; }
.reference { margin-left: 12.7mm; text-indent: -12.7mm; }
.apa-number { font-weight: bold; text-indent: 0; }
.apa-title { font-style: italic; text-indent: 0; }
table { border-collapse: collapse; width: 100%; font-size: 12pt; line-height: 1.2; }
th,td { padding: 3pt; border: 0; }
th { border-top: 1pt solid black; border-bottom: 1pt solid black; }
table tr:last-child td { border-bottom: 1pt solid black; }
figure { margin: 0; } figure img { max-width: 100%; }
figcaption { font-size: 11pt; line-height: 1.5; }
.docx-break { display: none; }
"""


def prepare():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manuscript = (SOURCE / "Informe_Gemelo_Digital_Cali.html").read_text(encoding="utf-8")
    manuscript = re.sub(
        r"<style>.*?</style>", "<style>" + CSS + "</style>", manuscript, count=1, flags=re.S
    )
    manuscript = re.sub(
        r'<section class="cover">.*?</section>',
        "<section><p>[[INSTITUTIONAL_COVER]]</p></section>",
        manuscript,
        count=1,
        flags=re.S,
    )
    manuscript = re.sub(
        r'<h1>Contenido</h1>\s*<div class="contents">.*?</div>', "", manuscript, flags=re.S
    )
    manuscript = re.sub(
        r'<p class="note">Las magnitudes reportadas.*?</p>', "", manuscript, flags=re.S
    )
    citations = {
        "sumo": "(Lopez et al., 2018)",
        "ppo": "(Schulman et al., 2017)",
        "sb3": "(Raffin et al., 2021)",
        "jain": "(Jain et al., 1984)",
        "osm": "(OpenStreetMap contributors, s. f.)",
        "sumorl": "(Alegre, 2019)",
    }
    for key, text in citations.items():
        manuscript = re.sub(rf'<a href="#ref-{key}">\[\d+\]</a>', text, manuscript)
    manuscript = re.sub(r"(<h[123][^>]*>)\d+(?:\.\d+)*\.?\s+", r"\1", manuscript)
    manuscript = manuscript.replace(
        "<h1>Introducción y objetivos</h1>", "<h1>Gemelo digital de movilidad urbana en Cali</h1>"
    )
    manuscript = re.sub(
        r'<section class="[^"]*refs">.*?</section>',
        '<section class="refs"><h1>Referencias</h1>' + REFERENCES + "</section>",
        manuscript,
        count=1,
        flags=re.S,
    )
    manuscript = manuscript.replace(
        "<h1>Anexo. Evidencia y reproducibilidad</h1>",
        "<h1>Apéndice A</h1><h1>Evidencia y reproducibilidad</h1>",
    )
    manuscript = manuscript.replace(
        "La fuente numérica primaria es el experimento completado",
        "El código del prototipo está disponible en el repositorio del proyecto "
        "(Quintero Estrada &amp; Arias Pantoja, 2026). "
        "La fuente numérica primaria es el experimento completado",
    )
    manuscript = re.sub(
        r'<p class="caption"><strong>Tabla (A?\d+)\.</strong>\s*(.*?)</p>',
        lambda match: f'<p class="apa-number">Tabla {match[1]}</p>'
        f'<p class="apa-title"><em>{match[2].rstrip(".")}</em></p>',
        manuscript,
        flags=re.S,
    )
    titles = {
        "1": "Red georreferenciada del corredor Roosevelt",
        "2": "Arquitectura y flujo de información del prototipo",
        "3": "Espera media por estrategia en la prueba final",
        "4": "Reducción de espera e intervalos de confianza de la prueba final",
    }

    def figure(match):
        number, note = match[3], match[4]
        return (
            f'<p class="apa-number">Figura {number}</p>'
            f'<p class="apa-title"><em>{titles[number]}</em></p>'
            f"<figure{match[1]}>{match[2]}<figcaption><em>Nota.</em> {note}</figcaption></figure>"
        )

    manuscript = re.sub(
        r"<figure([^>]*)>(<img[^>]*>)<figcaption><strong>Figura (\d+)\."
        r"</strong>\s*(.*?)</figcaption></figure>",
        figure,
        manuscript,
        flags=re.S,
    )
    manuscript = manuscript.replace("<strong>Palabras clave:</strong>", "<em>Palabras clave:</em>")
    assert not re.search(r"\[\d+\]", manuscript), "numeric citation left behind"
    assert manuscript.count('class="reference"') == 7
    (OUTPUT / "Informe_Gemelo_Digital_Cali_APA.html").write_text(manuscript, encoding="utf-8")
    shutil.copytree(SOURCE / "figures", OUTPUT / "figures", dirs_exist_ok=True)
    shutil.copytree(SOURCE / "evidence", OUTPUT / "evidence", dirs_exist_ok=True)
    print(f"APA manuscript ready: {OUTPUT}")


if __name__ == "__main__":
    prepare()
