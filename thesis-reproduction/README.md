# AGATA thesis reproduction

This package accompanies the 25 October 2026 thesis revision. It rebuilds the empirical figures and numeric time/resource tables from the published, processed data. It does not run agents, application scripts or GUI actions, and does not require access to the private session archive.

## Run

Use Python 3.10 or newer in an environment with NumPy and Matplotlib:

```sh
python -m pip install -r thesis-reproduction/requirements.txt
python thesis-reproduction/reproduce.py
```

Results are written below `thesis-reproduction/output/`: four thesis empirical figures (PDF and PNG), numeric LaTeX tables and `verification.json`. Additional legacy figure variants may also be generated. The scripts retain the thesis's plum/teal progress curves, observed sample sizes and fixed progress denominators. A freely distributed DejaVu Serif font replaces the locally used Times New Roman; coordinates and statistics are reproducible, while binary PDF identity and font metrics are not promised.

## Data and verification

`data/sessions.csv` contains all 112 inventory entries, of which 110 are included. It retains the numeric measurements, experimental groups and testcase hashes needed for the published comparisons, without original paths, testcase contents, conversation text or generated scripts. `data/metrics.json` retains only the run groups, numeric first-PASS times and the main exploration marker needed for the progress figures. `schema.json` lists public CSV columns.

Application/model summaries and progress curves come from the 8 October 2026 export. The later `phase_sessions.csv` and `command_errors.csv` are processed thesis supplements: phase intervals are heuristic estimates from workflow timestamps, and errors are the targeted, deduplicated command-error ledger. The original four route-audit cases are supplemented by the later Photos case R036, bringing the thesis's known GUI-route bypass count to five. These additions do not change the original time measurements or classify every unaudited script as compliant.

The reproduction checks the 35/39 main-group counts, all progress-curve means against individual numeric PASS times, Office group distributions, 20 application groups, eight model groups, five numeric table snapshots, 353 main-group command errors and five known route-audit cases. `reference_tables` preserves the published numeric and explanatory templates. The research-question table and error-table descriptions are editorial snapshots; their underlying numbers are checked rather than treating their prose as computed data.

## Access boundary

The raw session logs and original company-derived testcases are not public because they contain internal or execution-environment-specific material. Numerical summaries can be recomputed from this package; independently repeating raw-event extraction or validating GUI-route audit findings requires the original private records. The general analysis programs in `experiment-comparison` accept an archive supplied by the researcher. The published `examples/Word.csv` is a newly generalized illustration of the five-step structure, not an assertion that this exact wording was used in every historical run. Original testcase variants remain distinguishable by their recorded hashes.

Initial prompt variants are documented in `../experiment-comparison/initial-prompts-2026-10-24.txt`; analysis and extraction are described in `../experiment-comparison/README.md`. The original `tdk-2026-10-24` tag is preserved, and `tdk-2026-10-25-final` includes this supplement. Neither tag proves the precise historical code revision of every experiment.

## License

MIT, as stated in the repository's root `LICENSE`. The author confirmed applicability to the adapted PoTATo fragments. No third-party font files, raw logs or original company testcases are included.

The final snapshot pins LF line endings with `.gitattributes`; the entrypoint verifies the public data manifest before rebuilding results.
