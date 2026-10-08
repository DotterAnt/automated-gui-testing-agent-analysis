# Analysis And Dashboard

## Current Experiment Report

The 7 October 2026 analysis covers the current native, MCP, AI-only and new
Codex model experiments in `C:\Users\DottedAnt\Downloads\results`.
Open `analysis-output/batch-2026-10-07/report.html`, or the PDF at
`output/pdf/experiment-analysis-2026-10-07.pdf`. See
[experiment-comparison/README.md](experiment-comparison/README.md) for the
reproducible analysis command, exports and validation checks. Old and CLI
results are excluded from the current report.

## Historical Native / CLI + Framework Experiment Report

For the copied experiment bundles in `C:\Users\DottedAnt\Downloads\results`, see [experiment-comparison/README.md](experiment-comparison/README.md). The offline comparison opens at `analysis-output/experiment_comparison.html` and includes per-application graphs, token and iteration metrics, observed progress, sensitivity checks, and source evidence. Its input discovery includes only `native` and `cli`; `old` is excluded.

The analysis layer turns framework run folders into an interactive, standalone HTML dashboard.

## Build A Dashboard

```powershell
cd C:\diplomamunka\automated-gui-testing-agent-analysis
.\Invoke-BuildAnalysisDashboard.ps1 -Open
```

By default, the script reads runs from `..\automated-gui-testing-agent-framework\runs`. The output is written under `analysis-output\` in this folder. It can be opened directly in a browser and does not require a web server or JavaScript packages.

To compare copied session bundles such as `fullrun2`, `fullrun3`, and `fullrun4`, pass each folder as a run root:

```powershell
.\Invoke-BuildAnalysisDashboard.ps1 -RunsRoot C:\diplomamunka\fullrun2,C:\diplomamunka\fullrun3,C:\diplomamunka\fullrun4 -Open
```

The dashboard discovers direct run folders and nested `runs\<runId>` folders inside each supplied root. Pointing `-RunsRoot` at `C:\diplomamunka` is still useful for broad discovery, but it may include older or mock runs.

## Captured Metrics

The framework writes `logs\metrics.jsonl` in each run folder. Events currently include:

- `authoring_start`
- `authoring_end`
- `authoring_stage`
- `ai_response`
- `potato_command`
- `generated_script_run`

The PoTATo CLI also writes `metrics.jsonl` in its own run folder for direct CLI smoke tests.

The dashboard also reads generated script result files and command transcripts:

- `results\result.json`
- `logs\potato-commands-*.jsonl`
- legacy `logs\potato-commands.jsonl`

When session-based agents such as Codex are used, copy the raw `rollout-*.jsonl` file either into the run folder, the run folder's `logs` directory, or the parent runs folder. The analysis module matches rollout logs to runs by run id/path and extracts:

- total session duration,
- inferred Planning / Exploration / Development-Iteration durations,
- validation rerun count and failed validation runs,
- direct PoTATo exploration command count,
- generated-script runtime,
- total and largest tool-output size,
- cumulative token usage when present.

The stage chart is heuristic for session-agent rollouts because those logs do not explicitly mark framework stages. API authoring runs should prefer explicit `authoring_stage` events.

## Model Comparison

The dashboard includes a model comparison section above the per-run charts. It groups visible runs by provider and model, then shows:

- average Planning / Exploration / Development-Iteration duration,
- average overall runtime as a line chart and generated script runtime,
- average and total token use,
- total validation executions split into successful and failed executions,
- average final PoTATo command count,
- average direct CLI exploration commands,
- average tool output volume,
- run count, success rate, and estimated cost when pricing data is available.

The Provider, Model, Status, Search, and Sort controls still apply. Leave the Model filter on `All` when comparing models against each other.

## Cost Estimates

Token usage is read from OpenAI Responses API usage fields when available:

- `input_tokens`
- `input_tokens_details.cached_tokens`
- `output_tokens`
- `output_tokens_details.reasoning_tokens`
- `total_tokens`

Costs are calculated only when a pricing file is supplied. Copy `analysis-pricing.example.json`, add your own provider/model rates, and pass it with `-PricingPath`.

```powershell
.\Invoke-BuildAnalysisDashboard.ps1 -PricingPath .\analysis-pricing.local.json -Open
```

The pricing schema uses rates per 1 million tokens:

```json
{
  "currency": "USD",
  "unit": "per_1m_tokens",
  "models": {
    "model-name": {
      "input": 0.0,
      "cachedInput": 0.0,
      "output": 0.0
    }
  }
}
```

## External Agent Logs

For Codex/Copilot/Hermes-style session agents, keep raw logs under the run folder's `logs` directory or the parent runs folder. The dashboard consumes normalized framework metrics first and falls back to Codex rollout inference when explicit stage metrics are unavailable.
