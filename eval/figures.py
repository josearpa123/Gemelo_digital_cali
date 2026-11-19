"""Export comparable mean/std figures from completed evaluation rows."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot_summary(summary: list[dict], out: Path) -> None:
    scenarios = sorted({r["scenario"] for r in summary})
    for metric, label in (
        ("mean_wait", "Espera media (s)"),
        ("wait_p95", "Percentil 95 de espera (s)"),
        ("completed", "Viajes completados"),
    ):
        fig, axes = plt.subplots(1, len(scenarios), figsize=(6 * len(scenarios), 5), squeeze=False)
        for axis, scenario in zip(axes[0], scenarios, strict=True):
            rows = [r for r in summary if r["scenario"] == scenario]
            labels = [r["strategy"].replace("rl:ppo_roosevelt4_", "RL ") for r in rows]
            axis.bar(
                range(len(rows)),
                [r[f"{metric}_mean"] for r in rows],
                yerr=[r[f"{metric}_std"] for r in rows],
                capsize=4,
            )
            axis.set_xticks(range(len(rows)), labels, rotation=35, ha="right", fontsize=8)
            axis.set_title(scenario)
            axis.set_ylabel(label)
            axis.set_ylim(bottom=0)
            axis.grid(axis="y", alpha=0.2)
        fig.suptitle("Media ± desviación entre semillas de demanda")
        fig.tight_layout()
        fig.savefig(out / f"fig_{metric}.png", dpi=160)
        plt.close(fig)
