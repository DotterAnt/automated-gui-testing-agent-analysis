"""Build the F18 tables and check every statistic against the session export.

Only the two tables are updated; figures are not rebuilt.
"""
import argparse
import csv
import json
import math
from pathlib import Path
from statistics import fmean, median

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data"
TABLES = ROOT / "output/tables"
APPLICATIONS = ["Access", "Edge", "Excel", "Notepad", "OneNote", "Paint",
                "Photos", "PowerPoint", "Snipping Tool", "Word"]
MODELS = [("gpt-5.5", "GPT-5.5"), ("gpt-5.6-luna", "GPT-5.6 Luna"),
          ("gpt-6-luna", "GPT-6 Luna"), ("gpt-6.1-sol", "GPT-6.1 Sol")]


def number(value):
    return f"{float(value):.2f}".replace(".", ",")


def build_tables(source=SOURCE, tables=TABLES):
    def read(name):
        with (source / name).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    sessions = [r for r in read("sessions.csv") if r["included"] == "True"]
    applications = read("application_summary.csv")
    models = read("pooled_model_comparison.csv")
    evidence = {"application_groups": [], "model_groups": []}
    rows = [r"\begin{tabular}{@{}lrrrrrrrr@{}}", r"\toprule",
            r"Alkalmazás & \multicolumn{2}{c}{Ref.} & \multicolumn{2}{c}{AGATA} & \multicolumn{4}{c}{Idő (referencia / AGATA)} \\",
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(l){6-9}",
            r" & $n$ & Siker & $n$ & Siker & Átlag & Medián & Minimum & Maximum \\",
            r"\midrule"]
    for app in APPLICATIONS:
        pair = []
        for setup in ["native", "mcp"]:
            cohort = [r for r in sessions if r["model"] == "gpt-5.5" and
                      r["setup"] == setup and r["bucket"] == setup and r["app"] == app]
            values = [float(r["minutes"]) for r in cohort]
            record, = [r for r in applications if r["model"] == "gpt-5.5" and
                       r["setup"] == setup and r["app"] == app]
            n, successes = len(cohort), sum(r["success"] == "True" for r in cohort)
            stats = {"mean": fmean(values), "median": median(values),
                     "min": min(values), "max": max(values)}
            assert n == int(record["n"]) == int(record["minutes_n"])
            assert successes == int(record["successes"])
            for key, value in stats.items():
                assert math.isclose(value, float(record["minutes_" + key]), abs_tol=1e-10)
            evidence["application_groups"].append({"app": app, "setup": setup,
                "n": n, "full_five_row_signals": successes,
                "run_ids": [r["id"] for r in cohort], **stats})
            pair.append({"n": n, "successes": successes, **stats})
        left, right = pair
        cells = [app, str(left["n"]), str(left["successes"]),
                 str(right["n"]), str(right["successes"])]
        cells += [number(left[key]) + " / " + number(right[key])
                  for key in ["mean", "median", "min", "max"]]
        rows.append(" & ".join(cells) + r" \\")
    rows += [r"\bottomrule", r"\end{tabular}"]
    application_text = "\n".join(rows) + "\n"
    rows = [r"\begin{tabularx}{\textwidth}{@{}Xcrrrr@{}}", r"\toprule",
            r"Konfiguráció & $n$ & Ref. idő & Ref. siker & AGATA-idő & AGATA-siker \\",
            r"\midrule"]
    for model, name in MODELS:
        pair = []
        for setup in ["native", "mcp"]:
            record, = [r for r in models if r["model"] == model and r["setup"] == setup]
            cohort = [r for r in sessions if r["model"] == model and r["setup"] == setup and
                      r["app"] in ["Excel", "PowerPoint", "Word"]]
            n, successes = len(cohort), sum(r["success"] == "True" for r in cohort)
            assert n == int(record["n"]) and successes == int(record["successes"])
            assert {r["id"] for r in cohort} == set(json.loads(record["run_ids"]))
            app_means = {app: fmean(float(r["minutes"]) for r in cohort if r["app"] == app)
                         for app in ["Excel", "PowerPoint", "Word"]}
            mean = fmean(app_means.values())
            assert math.isclose(mean, float(record["mean_minutes"]), abs_tol=1e-10)
            pair.append({"n": n, "successes": successes, "mean": mean})
            evidence["model_groups"].append({"model": model, "setup": setup, "n": n,
                "full_five_row_signals": successes, "equal_application_mean_minutes": mean,
                "application_means": app_means, "run_ids": [r["id"] for r in cohort]})
        left, right = pair
        cells = [name, f"{left['n']} / {right['n']}", number(left["mean"]),
                 f"{left['successes']}/{left['n']}", number(right["mean"]),
                 f"{right['successes']}/{right['n']}"]
        rows.append(" & ".join(cells) + r" \\")
    rows += [r"\bottomrule", r"\end{tabularx}"]
    tables.mkdir(parents=True, exist_ok=True)
    (tables / "alkalmazasok.tex").write_text(application_text, encoding="utf-8", newline="\n")
    (tables / "modellek.tex").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    evidence = build_tables()
    if args.evidence:
        args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print("Built two descriptive tables; checked 20 application groups and 8 model groups against session data.")
