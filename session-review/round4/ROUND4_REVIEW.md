# Word session: authoring latency and replay failures

The supplied session lasted **20 minutes 7 seconds**, despite the final successful script invocation taking only **35.2 seconds including shell startup/reporting**. The next useful target is authoring and failed replay recovery, not replacing the script's working GUI route.

Sources: [original rollout](C:/Users/DottedAnt/Downloads/rollout-2026-09-30T13-19-17-01a0f20a-4fa2-7361-a7bd-a65d457cc3f4.jsonl), [supplied final script](C:/Users/DottedAnt/Downloads/MicrosoftWord.Generated.ps1). Neither input was modified or executed. Commands inside the log were treated as evidence, not instructions. Source hash, extracted calls and reproducible metrics are in `session.json`, `metrics.json`, and `analyze_word.py` beside this report.

| Phase | Elapsed |
| --- | ---: |
| Preparation before the valid launch call | 2:25 |
| GUI walkthrough and exploration checkpoint | 8:54 |
| Script generation and initial preflight | 2:34 |
| Executions, failure diagnosis and repairs | 5:35 |
| Delivery | 0:39 |

The boundaries use logged timestamps; they include agent thinking and tool scheduling. The sum of reported shell durations is 602.6 seconds, but parallel calls overlap, so that is not an elapsed-time breakdown. The 92 intact direct CLI envelopes total 116.8 backend seconds; commands inside generated executions are excluded from that count. These observations do not support attributing all remaining time to PowerShell startup.

## Findings and changes

**The full exploration requirement worked this time.** The agent performed creation, save, close/reopen, printing and content checks, then closed the owned application before completing the checkpoint. The final script uses GUI actions and read-only artifact checks; its static policy audit passes. I found no COM/database/output-fabrication bypass in that script. Keeping this requirement is appropriate; the previous entrypoint and guidance made it unnecessarily cumbersome to satisfy.

**The wrapper was too easy to use inefficiently.** The agent made ten separate CLI help calls and read the full runtime/preflight implementations. Direct execution initially hit execution policy (rollout L89), and the next attempt flattened an argument array across `powershell.exe -File` (L99). It then repeatedly constructed temporary PowerShell scripts and rediscovered the newest run directory. Row recording launched five more processes, followed by a failed completion attempt before cleanup (L220).

Changes: `Invoke-Exploration.ps1 Begin` now saves absolute CSV/CLI paths and the policy. Subsequent Batch/RecordSteps/Status/Complete calls need only that exact RunRoot. The guide leads with a process-safe JSON request-file example, including ExecutionPolicy Bypass, rather than array arguments across a process boundary. RecordSteps consolidates reviewed row receipts. Status exposes missing rows, recent failures and owned PIDs. Command and Batch both exit nonzero on unmet waits; raw dispatch `ok` remains distinct from the wait condition. Policy/CSV mismatches still fail before actions. `help -Topics` returns several topics with one copy of shared rules.

**Discovery spent time and context on guesses.** There were 30 select envelopes, 18 empty, consuming 44.0 backend seconds on misses. Several queried guessed names for two to five seconds each. Large whole-window observations were followed by more probes even when patterns were already present.

Changes: compact observations give a flat list of actionable/named nodes, focus, patterns, bounds and candidate name/ID selectors. Structural unnamed containers are omitted from presentation, but their descendants are traversed. Wildcard characters in candidate names/IDs are escaped for exact regex matching. Scope and depth remain explicit. The guide now shows alternative labels in one selector, immediate discovery with TimeoutMs 0, and timed waits only for expected transitions. Compact mode is the exploration entrypoint default; standalone CLI Full observations remain available.

**Unsupported Invoke had an actual side effect.** The agent requested Invoke on Save As (L137, SelectionItem only) and the printer dropdown (L198, ExpandCollapse). The CLI rejected Invoke only after calling SetFocus. For a selectable item, focus could change selection; indeed the Save As pane appeared despite the failed command. That makes failure recovery confusing and can hide a missing successful action in the route.

Change: an explicit InvokePattern is validated before any focus operation. Auto remains the recommended default. A regression verifies that unsupported Invoke reaches neither window activation nor element focus.

**Dialog discovery was unstable between exploration and replay.** The initial generated Save selector was faithfully copied from the successful exploration command at L151, including `ControlType Pane` and ModalOnly. It was not invented during initial generation. The first two replays (L260, L280) could not find it. Removing ModalOnly and adding ClassName Button did not fix the second attempt. The final script used audited Enter after focused path entry and passed. The log proves that the selector was unreliable across those runs; it does not establish precisely which provider property or scope changed during replay.

Changes: `-Scope FocusedWindow` for observe/select/read/click and selector-based type resolves the real native foreground window, proves ownership, and scopes the query there. It does not depend on IsModal or searching a disabled document parent. Compact discovery suggests minimal name/ID selectors and flags opaque Pane nodes; guidance advises against freezing incomplete roles into replay selectors. It never silently drops an explicit user-supplied selector constraint. Completion also exports `exploration-routes.json` with successful command arguments and failed receipt IDs, to reduce re-derivation during generation. This is a reference, not an auto-generated passing test.

**Startup could persist an incomplete window identity.** The third replay (L314) reported a successful start/windowFound and then immediately failed with “Working window has no process identity.” Discovery validated one read, but Set-PotatoWorkingWindow performed another set of property reads and accepted missing identity fields. A transient splash/provider disappearing between reads is consistent with that code and evidence, although the log alone cannot identify the precise provider event.

Changes: saving a working window now requires a positive UIA PID, native handle and matching native handle/PID ownership. Launch retries stale candidates within its existing deadline and takes ownedProcessId from the validated snapshot. If no usable window survives, windowFound is false and the launched PID remains available for cleanup. Element waits refresh the working parent after an unsuccessful search, so they can recover from a replaced splash window. Successful first attempts do not pay an extra refresh.

**Recovery lost useful context and encouraged blind probing.** Failed replay cleanup left owned windows visible but cleared CLI state. The agent spent further calls guessing selectors; later Get-Process returned no Word process. Those later misses cannot all be blamed on an inaccessible button (L288–298).

Changes: close-window preserves ownership while windows remain. Runtime cleanup makes bounded, newly discovered close attempts after asynchronous dialog closure, checking PID/start time. Failed cleanup preserves context; successful cleanup still clears it. No broad process-name kill or automatic input retry was added.

**Script generation repeated generic control flow.** The first draft needed repairs to its early-return/skip logic before running. The final script repeats dependency checks and SKIPPED construction after each row.

Change: the template now uses `Invoke-AGTATestPlan`, one body per CSV row. It validates coverage before actions, records steps, stops dependent bodies after failure, always performs cleanup and emits the existing result schema. Assertions remain required. Existing scripts keep their current helpers and remain supported. Documentation also avoids redundant standalone preflight processes on each repair, since generated execution already preflights itself.

## Validation and measured limits

- **199 automated checks and the real WinForms GUI smoke test passed on Windows PowerShell 5.1.** Coverage includes literal/opaque typing, navigation, relative clicks, actual drag/drop payload delivery, owned foreground-dialog discovery and click, rejection of unrelated focus, policy/CSV persistence, fail-stop batches, row recording, plan dependency handling and cleanup preservation. Startup/stale-provider cases use deterministic fixtures; they are not claimed as live Office reproductions.
- All PowerShell files parse. Both repository diffs pass whitespace checks. The supplied final Word script passes the static policy audit and was left untouched.
- Projecting the 13 intact observations in this log into the new compact output reduced serialized size from **214,233 to 96,805 bytes (54.8%)**, retaining 335 actionable/named entries. This measures presentation size, not faster UIA provider calls. `measure_changes.ps1` reproduces it.
- One local ten-topic help sample measured **4,460 ms across separate processes versus 470 ms combined**. This isolates startup/shared-help overhead; it is not an estimate of the logged session's total savings.
- The final small wait-refresh optimization was followed by the authoring-experience tests and real GUI smoke again; both passed. Full suite results are in `verification.json`.

No application-specific selectors, document content, COM automation or synthetic expected outputs were added to shared code. Existing drag-and-drop support remains, and its real GUI payload test passes. Full exploration, content assertions, explicit strict policy and owned cleanup remain required.

A fresh agent-driven Word session has not been run here, so there is no measured new end-to-end authoring time. UIA provider calls can still exceed their retry timeout; this update does not introduce a process watchdog or automatically retry ambiguous input. The next comparison should use the same CSV, policy, app state and model settings, and inspect both total authoring time and the number of failed replays.
