"""Build the thesis figures and tables from the dated experiment exports."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from build_descriptive_tables import build_tables

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data"
FIGURES = ROOT / "output" / "images"
TABLES = ROOT / "output" / "tables"
FIGURES.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(parents=True, exist_ok=True)

def read(name):
    with (SOURCE / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def number(value):
    return f"{float(value):.2f}".replace(".", ",")

plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 10,
                     "pdf.fonttype": 42, "ps.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False})
COLORS = ["#727b86", "#245f87", "#af762e"]
applications = read("application_summary.csv")
comparisons = read("comparisons.csv")
models = read("pooled_model_comparison.csv")
labels = ["Access", "Edge", "Excel", "Notepad", "OneNote", "Paint",
          "Photos", "PowerPoint", "Snipping Tool", "Word"]
def app_record(app, setup):
    return next(r for r in applications if r["app"] == app and r["model"] == "gpt-5.5" and r["setup"] == setup)

build_tables(SOURCE, TABLES)

fig, ax = plt.subplots(figsize=(9.2, 6.4))
y = np.arange(len(labels))
for offset, setup, color, label in [(-0.18, "native", COLORS[0], "Referenciaeljárás"),
                                   (0.18, "mcp", COLORS[1], "AGATA")]:
    values = [float(app_record(a, setup)["minutes_mean"]) for a in labels]
    ax.barh(y + offset, values, height=0.34, color=color, label=label)
    for pos, value, app in zip(y + offset, values, labels):
        ax.text(value + 0.7, pos, "n=" + app_record(app, setup)["n"], va="center", fontsize=9)
ax.set_yticks(y, labels)
ax.invert_yaxis()
ax.set_xlim(0, 95)
ax.set_xlabel("Átlagos előállítási idő (perc)")
ax.legend(loc="lower right", frameon=False)
ax.xaxis.grid(True, alpha=0.2)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(FIGURES / "alkalmazasok.png", dpi=220)
plt.close(fig)

office = next(r for r in comparisons if r["label"] == "GPT-5.5 shared Office apps")
ai = next(r for r in comparisons if r["label"] == "AI-only versus MCP on Office")
values = [float(office["left_mean"]), float(office["right_mean"]), float(ai["right_mean"])]
counts = [office["left_n"], office["right_n"], ai["right_n"]]
fig, ax = plt.subplots(figsize=(8.4, 4.4))
ax.bar(["Referenciaeljárás", "AGATA", "MI-megvalósítás"], values, color=COLORS, width=0.6)
for i, (value, count) in enumerate(zip(values, counts)):
    ax.text(i, value + 0.8, f"{number(value)} perc\nn={count}", ha="center", fontsize=11)
ax.set_ylim(0, 39)
ax.set_ylabel("Átlagos előállítási idő (perc)")
ax.yaxis.grid(True, alpha=0.2)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(FIGURES / "office_eljarasok.png", dpi=220)
plt.close(fig)

model_ids = ["gpt-5.5", "gpt-5.6-luna", "gpt-6-luna", "gpt-6.1-sol"]
names = ["GPT-5.5", "GPT-5.6 Luna", "GPT-6 Luna", "GPT-6.1 Sol"]
def model_record(model, setup):
    return next(r for r in models if r["model"] == model and r["setup"] == setup)
fig, ax = plt.subplots(figsize=(9.2, 4.7))
x = np.arange(len(model_ids))
for offset, setup, color, label in [(-0.18, "native", COLORS[0], "Referenciaeljárás"),
                                   (0.18, "mcp", COLORS[1], "AGATA")]:
    for i, mid in enumerate(model_ids):
        record = model_record(mid, setup)
        value = float(record["mean_minutes"])
        hatch = "///" if int(record["successes"]) < int(record["n"]) else None
        ax.bar(i + offset, value, width=0.34, color=color, hatch=hatch,
               label=label if i == 0 else None, edgecolor="#4b5563", linewidth=0.5)
        ax.text(i + offset, value + 0.6, f"{record['successes']}/{record['n']}", ha="center", fontsize=10)
ax.set_xticks(x, names)
ax.set_ylim(0, 38)
ax.set_ylabel("Átlagos előállítási idő (perc)")
ax.legend(frameon=False)
ax.yaxis.grid(True, alpha=0.2)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(FIGURES / "office_modellek.png", dpi=220)
plt.close(fig)


# New thesis figures use the original exports, including the recorded denominators.
curves = read("progress_curves.csv")
sessions = read("sessions.csv")
audit_ids = {row["run_id"] for row in read("route_audits.csv")}
metrics = json.loads((SOURCE / "metrics.json").read_text(encoding="utf-8"))
styles = {"native": "--", "mcp": "-", "aionly": ":"}
colors = dict(zip(["native", "mcp", "aionly"], COLORS))
names_by_setup = {"native": "Referencia", "mcp": "AGATA", "aionly": "MI-megvalósítás"}
checks = {"progress": {}, "office_counts": {}}

def save_publication(fig, name):
    fig.savefig(FIGURES / (name + ".pdf"))
    fig.savefig(FIGURES / (name + ".png"), dpi=240)
    plt.close(fig)

def selected_runs(comparison):
    return [run for run in metrics["runs"] if run["included"] and
            run["model"] == "gpt-5.5" and
            run["bucket"] in (["native", "mcp"] if comparison == "baseline-progress" else ["native", "mcp", "aionly"]) and
            (comparison == "baseline-progress" or run["app"] in ["Excel", "PowerPoint", "Word"])]

def progress_figure(comparison, name):
    plot_colors = dict(colors)
    if comparison == "baseline-progress":
        plot_colors["native"] = "#8B3F75"
        plot_colors["mcp"] = "#007F73"
    individual_alpha = 0.22 if comparison == "baseline-progress" else 0.065
    individual_width = 0.65 if comparison == "baseline-progress" else 0.55
    groups = ["native", "mcp"] if comparison == "baseline-progress" else ["native", "mcp", "aionly"]
    sample = selected_runs(comparison)
    fig, ax = plt.subplots(figsize=(6.3, 2.85))
    for group in groups:
        cohort = [run for run in sample if run["setup"] == group]
        source_rows = [row for row in curves if row["comparison"] == comparison and
                       row["application"] == "all" and row["setup"] == group]
        times = np.array([float(row["minutes"]) for row in source_rows])
        values = np.array([float(row["mean_observed_rows"]) for row in source_rows])
        assert {int(row["tasks"]) for row in source_rows} == {len(cohort)}
        reconstructed = np.mean([[sum(point["minutes"] <= t for point in run["first_pass"].values())
                                  for t in times] for run in cohort], axis=0)
        assert np.allclose(values, reconstructed, atol=1e-12)
        checks["progress"][comparison + "/" + group] = {
            "tasks": len(cohort), "export_points": len(times),
            "max_mean_error": float(np.max(np.abs(values - reconstructed)))}
        for run in cohort:
            event_times = sorted({0.0, 60.0, *[point["minutes"] for point in run["first_pass"].values()]})
            levels = [sum(point["minutes"] <= t for point in run["first_pass"].values()) for t in event_times]
            ax.step(event_times, levels, where="post", color=plot_colors[group],
                    linestyle=styles[group], lw=individual_width, alpha=individual_alpha, zorder=1)
            if run["minutes"] > 60 and comparison == "baseline-progress":
                level = sum(point["minutes"] <= 60 for point in run["first_pass"].values())
                ax.plot(60, level, marker=">", color=plot_colors[group], ms=5.5,
                        clip_on=False, zorder=5)
        ax.step(times, values, where="post", color=plot_colors[group], linestyle=styles[group],
                lw=1.9, label=f"{names_by_setup[group]} (n={len(cohort)})", zorder=3)
    ax.set(xlim=(0, 60), ylim=(-0.02, 5.15), yticks=range(6),
           xlabel="A feladat kezdetétől eltelt idő (perc)",
           ylabel="Sikeresnek jelzett\ntesztlépések száma")
    ax.grid(alpha=0.16, lw=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", fontsize=8.7, framealpha=0.97, edgecolor="#dddddd")
    if comparison == "baseline-progress":
        timing = metrics["baseline_exploration_completion"]
        marker = timing["mean_minutes"]
        ax.axvline(marker, color=plot_colors["mcp"], ls=":", lw=1)
        ax.text(marker + 0.4, 1.035,
                f"Feltárás lezárása: {number(marker)} perc ({timing['n']}/{timing['total']})",
                transform=ax.get_xaxis_transform(), color=plot_colors["mcp"], fontsize=9)
        checks["exploration"] = timing
    fig.subplots_adjust(left=0.105, right=0.975, bottom=0.2, top=0.89 if comparison == "baseline-progress" else 0.96)
    save_publication(fig, name)

progress_figure("baseline-progress", "teljes_elorehaladas")
progress_figure("office-progress", "office_elorehaladas")

fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.95), sharey=True)
for ax, app in zip(axes, ["Excel", "PowerPoint", "Word"]):
    for x, setup in enumerate(["native", "mcp", "aionly"]):
        cohort = [row for row in sessions if row["included"] == "True" and row["model"] == "gpt-5.5" and row["setup"] == setup and row["app"] == app]
        values = [float(row["minutes"]) for row in cohort]
        expected = next(row for row in applications if row["model"] == "gpt-5.5" and row["setup"] == setup and row["app"] == app)
        assert len(cohort) == int(expected["n"])
        assert np.isclose(np.mean(values), float(expected["minutes_mean"]), atol=1e-10)
        checks["office_counts"][app + "/" + setup] = len(cohort)
        ax.bar(x, np.mean(values), color=colors[setup], alpha=0.46, width=0.65, zorder=2)
        offsets = np.linspace(-0.16, 0.16, len(cohort)) if len(cohort) > 1 else [0]
        for offset, row, value in zip(offsets, cohort, values):
            if row["id"] in audit_ids:
                ax.scatter(x + offset, value, marker="x", c="#343434", s=26, linewidths=1, zorder=5)
            else:
                ax.scatter(x + offset, value, c=colors[setup], edgecolors="white", linewidths=0.6, s=24, zorder=4)
        ax.text(x, max(values) + 2.0, "n=" + str(len(cohort)), ha="center", fontsize=8.5)
    ax.set_title(app, fontsize=10.5, pad=7)
    ax.set_xticks(range(3), ["Ref.", "AGATA", "MI"], rotation=15)
    ax.set_ylim(0, 63)
    ax.set_yticks(range(0, 61, 15))
    ax.grid(axis="y", alpha=0.16, lw=0.5)
    ax.set_axisbelow(True)
axes[0].set_ylabel("Előállítási idő (perc)")
fig.subplots_adjust(left=0.09, right=0.99, bottom=0.22, top=0.87, wspace=0.12)
save_publication(fig, "office_eljarasok_reszletes")

manifest = {"source_export": "data", "analysis_updated": "2026-10-08",
            "duration_weighting": "equal application means",
            "progress_weighting": "equal tasks; fixed denominator; held endpoints", "files": {}}
for name in ["application_summary.csv", "comparisons.csv", "pooled_model_comparison.csv", "summary.csv",
             "route_audits.csv", "progress_curves.csv", "sessions.csv", "exploration_completion.csv", "metrics.json"]:
    manifest["files"][name] = hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
(ROOT / "output" / "data_provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ROOT / "output" / "figure_data_checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Built the thesis figures and tables; all progress means and Office distributions match the analysis exports.")
