"""Standalone stage-coverage figure; plotting dependencies stay in diagnostics."""

import base64
import json
import sys
from pathlib import Path

OUT = Path("data/diagnostics/eval-v2")
sys.path.insert(0, str((OUT / "plot-deps").resolve()))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    rows = json.loads((OUT / "stage_summary.json").read_text(encoding="utf-8"))
    ordinary = [r for r in rows if r["experiment"] == "E3"]
    oracle = [r for r in rows if r["experiment"] == "E4"]
    if len(oracle) != 20:
        oracle = [r for r in rows if r["experiment"] == "E4trace"]
    assert len(ordinary) == len(oracle) == 20
    keys = ("all_in_expansion", "all_in_fact_score_top20", "all_in_top20")
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
    for offset, values, label, color, hatch in (
        (-0.19, ordinary, "Ordinary seeds", "#2563a6", ""),
        (0.19, oracle, "Gold MENTIONS seeds", "#bc5b19", "//"),
    ):
        counts = [sum(r[k] for r in values) for k in keys]
        bars = ax.bar(
            x + offset,
            counts,
            0.34,
            label=label,
            color=color,
            hatch=hatch,
            edgecolor="white",
        )
        ax.bar_label(bars, labels=[f"{n}/20" for n in counts], padding=4, fontsize=11)
    ax.set_xticks(x, ("Two-hop expansion", "Fact-score top 20", "Fused top 20"))
    ax.set_ylim(0, 22)
    ax.set_yticks((0, 5, 10, 15, 20))
    ax.set_ylabel("Questions with every gold item represented")
    ax.set_title(
        "Own-mode losses before and after ranking", loc="left", fontsize=15, pad=18
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.11), ncols=2)
    fig.savefig(OUT / "stage-coverage.png", dpi=180, facecolor="white")
    fig.savefig(OUT / "stage-coverage.svg", facecolor="white")
    plt.close(fig)
    data = base64.b64encode((OUT / "stage-coverage.png").read_bytes()).decode()
    (OUT / "stage-coverage.html").write_text(
        '<div style="max-width:1000px;margin:0 auto"><img alt="All-bubble own retrieval: full gold coverage with ordinary versus oracle seeds, before and after fusion" style="display:block;width:100%;height:auto" src="data:image/png;base64,'
        + data
        + '"></div>',
        encoding="utf-8",
    )
    print((OUT / "stage-coverage.png").resolve())


if __name__ == "__main__":
    main()
