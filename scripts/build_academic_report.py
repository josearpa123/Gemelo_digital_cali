"""Build an evidence-backed academic report manuscript and figures inside Docker."""

import argparse
import csv
import hashlib
import html
import json
import shutil
import statistics
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ORDER = ("peak", "valley", "event")
NAMES = {"peak": "Pico", "valley": "Valle", "event": "Evento"}
COLORS = {"fixed": "#667785", "maxpressure": "#c78332", "rl": "#117d83"}
AUTHORS = ("Milton Alberto Quintero Estrada", "Jose David Arias Pantoja")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fmt(value, digits=2):
    return f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def percent(value):
    return fmt(value * 100, 1) + " %"


def ci(row):
    return f"[{fmt(row['ci95_low'] * 100, 1)}; {fmt(row['ci95_high'] * 100, 1)}] %"


def table(headers, rows, numeric=()):
    head = "<thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead>"
    body = []
    for row in rows:
        cells = [
            f'<td class="{"num" if i in numeric else ""}">{html.escape(str(v))}</td>'
            for i, v in enumerate(row)
        ]
        body.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + head + "<tbody>" + "".join(body) + "</tbody></table>"


def save_figure(fig, path):
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figures(out, report, selection, state):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelcolor": "#263f4b",
            "text.color": "#263f4b",
        }
    )
    rows = {
        (r["scenario"], "rl" if r["strategy"].startswith("rl:") else r["strategy"]): r
        for r in report["summary"]
    }
    fig, axis = plt.subplots(figsize=(7.4, 3.55))
    x = np.arange(3)
    for index, (strategy, label) in enumerate(
        (("fixed", "Tiempo fijo"), ("maxpressure", "Max-pressure"), ("rl", "PPO seleccionado"))
    ):
        values = [rows[(sc, strategy)]["mean_wait_mean"] for sc in ORDER]
        errors = [rows[(sc, strategy)]["mean_wait_std"] for sc in ORDER]
        axis.bar(
            x + (index - 1) * 0.24,
            values,
            width=0.23,
            yerr=errors,
            capsize=3,
            label=label,
            color=COLORS[strategy],
            zorder=3,
        )
    axis.set_xticks(x, [NAMES[sc] for sc in ORDER])
    axis.set_ylabel("Espera media por viaje (s)")
    axis.grid(axis="y", alpha=0.18, zorder=0)
    axis.set_ylim(0, 77)
    axis.legend(loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.14))
    fig.tight_layout()
    save_figure(fig, out / "espera_final.png")

    comparisons = {(r["scenario"], r["baseline"]): r for r in report["comparisons"]}
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    for axis, reference, title in zip(
        axes,
        ("fixed", "maxpressure"),
        ("Frente a tiempo fijo", "Frente a max-pressure"),
        strict=True,
    ):
        for i, sc in enumerate(ORDER):
            item = comparisons[(sc, reference)]
            mean, low, high = (item[k] * 100 for k in ("wait_reduction", "ci95_low", "ci95_high"))
            axis.errorbar(
                mean,
                2 - i,
                xerr=[[mean - low], [high - mean]],
                fmt="o",
                capsize=4,
                color="#117d83",
                markersize=5,
            )
            axis.annotate(
                f"{mean:.1f}%".replace(".", ","),
                (mean, 2 - i),
                xytext=(0, 9),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
        axis.set_yticks([2, 1, 0], [NAMES[sc] for sc in ORDER])
        axis.set_ylim(-0.5, 2.6)
        axis.set_title(title, fontsize=10, pad=10)
        axis.set_xlabel("Reducción de espera (%)")
        axis.axvline(0, color="#82939b", linewidth=1, linestyle="--")
        axis.grid(axis="x", alpha=0.15)
    axes[0].set_xlim(0, 82)
    axes[1].set_xlim(-8, 40)
    fig.tight_layout(w_pad=2)
    save_figure(fig, out / "reducciones_finales.png")

    scores = {r["model"]: r["score"] for r in selection["candidates"]}
    fig, axis = plt.subplots(figsize=(6.8, 2.45))
    for index, alpha in enumerate((0.0, 0.3)):
        group = sorted((r for r in state["models"] if r["alpha"] == alpha), key=lambda r: r["seed"])
        values = [scores[r["path"]] for r in group]
        for offset, run, score in zip((-0.08, 0, 0.08), group, values, strict=True):
            axis.scatter(index + offset, score, s=40, color="#117d83", zorder=3)
            axis.annotate(
                f"s{run['seed']}",
                (index + offset, score),
                xytext=(6, 3),
                textcoords="offset points",
                fontsize=8,
            )
        axis.errorbar(
            index,
            statistics.fmean(values),
            yerr=statistics.stdev(values),
            fmt="_",
            color="#163e55",
            markersize=30,
            linewidth=1.5,
            capsize=8,
        )
    axis.set_xticks([0, 1], ["α = 0", "α = 0,3"])
    axis.set_xlim(-0.45, 1.45)
    axis.set_ylabel("Score normalizado de validación\n(menor es mejor)")
    axis.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    save_figure(fig, out / "score_validacion.png")

    fig, axis = plt.subplots(figsize=(7.4, 2.5))
    axis.set_xlim(0, 10)
    axis.set_ylim(0, 4)
    axis.axis("off")
    nodes = [
        ((0.1, 2.3), "Red OSM\ny demanda"),
        ((3.6, 2.3), "SUMO\ny controladores"),
        ((7.1, 2.3), "API y panel\nEstado y trazas"),
        ((0.1, 0.2), "Entrenamiento\nPPO compartido"),
        ((3.6, 0.2), "Modelos\ny configuración"),
        ((7.1, 0.2), "Validación\ny prueba final"),
    ]
    for (px, py), label in nodes:
        axis.add_patch(
            FancyBboxPatch(
                (px, py),
                2.7,
                1.2,
                boxstyle="round,pad=0.06",
                facecolor="#edf4f5",
                edgecolor="#7899a5",
                linewidth=1,
            )
        )
        axis.text(px + 1.35, py + 0.6, label, ha="center", va="center", fontsize=9)
    for start, end in [
        ((2.9, 2.9), (3.45, 2.9)),
        ((6.4, 2.9), (6.95, 2.9)),
        ((1.45, 2.2), (1.45, 1.5)),
        ((2.9, 0.8), (3.45, 0.8)),
        ((6.4, 0.8), (6.95, 0.8)),
        ((4.95, 1.5), (4.95, 2.2)),
    ]:
        axis.add_patch(
            FancyArrowPatch(
                start, end, arrowstyle="-|>", color="#315e70", mutation_scale=12, linewidth=1.2
            )
        )
    save_figure(fig, out / "arquitectura.png")


def build(root: Path, output: Path, academic_details=""):
    state = read_json(root / "experiment.json")
    validation = read_json(root / "validation/report.json")
    final = read_json(root / "test/report.json")
    selection = read_json(root / "selection.json")
    assert state["status"] == "completed" and len(state["models"]) == 6
    assert validation["split"] == "validation" and validation["seeds"] == list(range(200, 205))
    assert final["status"] == "completed" and final["split"] == "test"
    assert final["seeds"] == list(range(300, 305)) and final["seconds"] == 3600
    assert final["models"] == [selection["selected_model"]]
    assert datetime.fromisoformat(selection["selected_utc"]) <= datetime.fromisoformat(
        final["started_utc"]
    )
    model_path = Path(selection["selected_model"]) / "model.zip"
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == selection["model_sha256"]
    for stage, count in (("validation", 120), ("test", 45)):
        with (root / stage / "runs.csv").open() as source:
            assert len(list(csv.DictReader(source))) == count
    configs = {run["path"]: read_json(Path(run["path"]) / "config.json") for run in state["models"]}
    assert all(
        c["status"] == "completed" and c["actual_timesteps"] == 3000320 for c in configs.values()
    )
    output.mkdir(parents=True, exist_ok=True)
    image_dir = output / "figures"
    image_dir.mkdir(exist_ok=True)
    figures(image_dir, final, selection, state)
    shutil.copy2("docs/img/roosevelt4_sumo.png", image_dir / "corredor.png")
    values = {}
    rows = {
        (r["scenario"], "rl" if r["strategy"].startswith("rl:") else r["strategy"]): r
        for r in final["summary"]
    }
    compared = {(r["scenario"], r["baseline"]): r for r in final["comparisons"]}
    values["peak_fixed_reduction"] = percent(compared[("peak", "fixed")]["wait_reduction"])
    values["peak_mp_reduction"] = percent(compared[("peak", "maxpressure")]["wait_reduction"])
    values["valley_mp_reduction"] = percent(compared[("valley", "maxpressure")]["wait_reduction"])
    values["peak_fixed_ci"] = ci(compared[("peak", "fixed")])
    values["valley_mp_ci"] = ci(compared[("valley", "maxpressure")])
    values["peak_fixed_travel"] = fmt(rows[("peak", "fixed")]["mean_travel_time_mean"])
    values["peak_rl_travel"] = fmt(rows[("peak", "rl")]["mean_travel_time_mean"])
    values["academic_details"] = (
        f'<p class="academic-details">{html.escape(academic_details)}</p>'
        if academic_details
        else ""
    )
    values["hyperparameters_table"] = table(
        ["Parámetro", "Valor común"],
        [
            ("Algoritmo y política", "PPO con MlpPolicy y parámetros compartidos"),
            ("Tasa de aprendizaje", "0,0003"),
            ("Descuento γ", "0,99"),
            ("Coeficiente de entropía", "0,01"),
            ("Pasos por rollout y entorno", "256"),
            ("Tamaño de lote", "256"),
            ("Épocas por actualización", "5"),
            ("Entornos de simulación paralelos", "2"),
            ("Presupuesto solicitado por corrida", "3.000.000 pasos"),
            ("Duración de episodio / intervalo de decisión", "3600 s / 5 s"),
        ],
    )
    values["splits_table"] = table(
        ["Uso", "Semillas de demanda", "Escenarios", "Archivos"],
        [
            ("Entrenamiento", "100–119", "Pico, valle y evento", "60"),
            ("Validación", "200–204", "Pico, valle y evento", "15"),
            ("Prueba final", "300–304", "Pico, valle y evento", "15"),
        ],
        numeric=(3,),
    )
    score_by_model = {r["model"]: r for r in selection["candidates"]}
    values["runs_table"] = table(
        ["α", "Semilla", "Pasos reales", "Entrenamiento (min)", "Score"],
        [
            (
                fmt(run["alpha"], 1),
                run["seed"],
                fmt(configs[run["path"]]["actual_timesteps"], 0),
                fmt(configs[run["path"]]["wall_seconds"] / 60, 1),
                fmt(score_by_model[run["path"]]["score"], 6),
            )
            for run in state["models"]
        ],
        numeric=(0, 1, 2, 3, 4),
    )
    groups = {
        alpha: [score_by_model[r["path"]]["score"] for r in state["models"] if r["alpha"] == alpha]
        for alpha in (0.0, 0.3)
    }
    values["families_table"] = table(
        ["Configuración", "Entrenamientos", "Score medio", "Desviación"],
        [
            (
                f"α = {fmt(alpha, 1)}",
                3,
                fmt(statistics.fmean(scores), 4),
                fmt(statistics.stdev(scores), 4),
            )
            for alpha, scores in groups.items()
        ],
        numeric=(1, 2, 3),
    )
    values["family_difference"] = percent(
        1 - statistics.fmean(groups[0.3]) / statistics.fmean(groups[0.0])
    )
    values["selected_score"] = fmt(score_by_model[selection["selected_model"]]["score"], 6)
    values["wait_table"] = table(
        ["Escenario", "Tiempo fijo", "Max-pressure", "PPO elegido"],
        [
            (
                NAMES[sc],
                *(
                    f"{fmt(rows[(sc, st)]['mean_wait_mean'])} ± "
                    f"{fmt(rows[(sc, st)]['mean_wait_std'])}"
                    for st in ("fixed", "maxpressure", "rl")
                ),
            )
            for sc in ORDER
        ],
        numeric=(1, 2, 3),
    )
    values["reductions_table"] = table(
        ["Escenario", "Frente a fijo", "IC 95 %", "Frente a max-pressure", "IC 95 %"],
        [
            (
                NAMES[sc],
                percent(compared[(sc, "fixed")]["wait_reduction"]),
                ci(compared[(sc, "fixed")]),
                percent(compared[(sc, "maxpressure")]["wait_reduction"]),
                ci(compared[(sc, "maxpressure")]),
            )
            for sc in ORDER
        ],
        numeric=(1, 2, 3, 4),
    )
    for key, metric, digits in (
        ("travel_table", "mean_travel_time_mean", 2),
        ("fairness_table", "jain_wait_mean", 3),
    ):
        values[key] = table(
            ["Escenario", "Tiempo fijo", "Max-pressure", "PPO elegido"],
            [
                (
                    NAMES[sc],
                    *(fmt(rows[(sc, st)][metric], digits) for st in ("fixed", "maxpressure", "rl")),
                )
                for sc in ORDER
            ],
            numeric=(1, 2, 3),
        )
    values["support_table"] = table(
        [
            "Escenario",
            "P95 espera (s)",
            "Cola máxima (veh.)",
            "Viajes completados",
            "Teletransportes",
        ],
        [
            (
                NAMES[sc],
                fmt(rows[(sc, "rl")]["wait_p95_mean"]),
                fmt(rows[(sc, "rl")]["queue_max_mean"], 1),
                fmt(rows[(sc, "rl")]["completed_mean"], 1),
                fmt(rows[(sc, "rl")]["teleports_mean"], 0),
            )
            for sc in ORDER
        ],
        numeric=(1, 2, 3, 4),
    )
    values["evidence_table"] = table(
        ["Artefacto", "Contenido verificable"],
        [
            ("experiment.json", "Protocolo, estado completed y seis modelos"),
            ("validation/runs.csv y report.json", "120 corridas con semillas 200–204"),
            ("selection.json", "Candidato, regla y hashes fijados antes del test"),
            ("test/runs.csv y report.json", "45 corridas con semillas 300–304"),
            ("test/goal_check.md", "Comprobación del objetivo de reducción de espera"),
            ("source/ y git-revision.txt", "Código y datos de entrada congelados"),
            ("container-exit-code.log", "Finalización del proceso con código 0"),
        ],
    )
    versions = final["provenance"]["versions"]
    values["versions_table"] = table(["Componente", "Versión registrada"], versions.items())
    values["total_steps"] = fmt(sum(c["actual_timesteps"] for c in configs.values()), 0)
    values["steps_per_run"] = fmt(3000320, 0)
    values["selected_model"] = html.escape(selection["selected_model"])
    values["model_sha256"] = selection["model_sha256"]
    values["source_revision"] = (root / "git-revision.txt").read_text().strip()
    manuscript = Path("scripts/academic_report.html").read_text(encoding="utf-8")
    for key, value in values.items():
        manuscript = manuscript.replace("{{" + key + "}}", value)
    assert "{{" not in manuscript, "unresolved report field"
    (output / "Informe_Gemelo_Digital_Cali.html").write_text(manuscript, encoding="utf-8")
    evidence = output / "evidence"
    evidence.mkdir(exist_ok=True)
    for path in (
        "experiment.json",
        "experiment.md",
        "selection.json",
        "git-revision.txt",
        "image-id.txt",
        "container-exit-code.log",
        "validation/runs.csv",
        "validation/summary.csv",
        "validation/report.json",
        "validation/goal_check.md",
        "test/runs.csv",
        "test/summary.csv",
        "test/report.json",
        "test/goal_check.md",
    ):
        target = evidence / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, target)
    build_info = {
        "authors": AUTHORS,
        "experiment": str(root),
        "selected_model": selection["selected_model"],
        "training_models": 6,
        "total_training_steps": sum(c["actual_timesteps"] for c in configs.values()),
        "validation_runs": 120,
        "test_runs": 45,
        "final_comparisons": final["comparisons"],
        "source_validation": "passed",
    }
    (output / "build-info.json").write_text(
        json.dumps(build_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({"output": str(output), "source_validation": "passed", "authors": AUTHORS}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment", type=Path, default=Path("outputs/evaluations/cooperation_20261119")
    )
    parser.add_argument("--output", type=Path, default=Path("outputs/report_20261119"))
    parser.add_argument("--academic-details", default="")
    args = parser.parse_args()
    build(args.experiment, args.output, args.academic_details)
