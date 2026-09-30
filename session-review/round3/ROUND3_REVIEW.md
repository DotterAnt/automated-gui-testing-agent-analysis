# Session review and implementation — 30 September 2026

The largest opportunities are reducing failed discovery/repair cycles and repeated shell round trips. In-process execution already existed; replacing it was not the missing optimization. The framework also accepted misleading PASS results because it checked recorded CLI commands but did not audit direct application automation or require evidence of a complete exploration.

## Evidence and scope

The supplied rollouts and scripts were read as data, never executed. `analyze_sessions.py` indexes Downloads/results and the older experiments, records source hashes and original one-based event lines, extracts command results and failures, and flags duplicate logs. The detailed review focuses on CLI/framework runs, their final scripts, and relevant native comparisons. See `metrics.json`, per-session text extracts, and `script-policy-audit.json`.

`test29-cli-frm-excel-23m` and `test30-cli-frm-excel-23m` contain identical rollout and script content. They are one observation, not two independent successes. Folder names are not trustworthy timing or correctness labels: the Snipping Tool log labelled 47 minutes spans about 342 minutes including later activity. A final PASS also does not establish that the required route was exercised.

## What went wrong

| Finding | Evidence in original rollout/script | Consequence |
|---|---|---|
| Exploration was advisory and sometimes skipped | Previous AUTHORING.md said “Explore only unknown transitions.” PowerPoint test34 L64–106 writes the script before live exploration; L148 and L172 then discover guessed roles were wrong. Access test32 L169 starts development before proving reopen/print. | Avoidable full-run failures and repeated authoring cycles. |
| PASS could be produced outside the tested GUI | Excel test28 L206 explicitly identifies the missing preflight check and switches to Office automation; its script L53/56 uses GetActiveObject/COM. Access test31 script L43–69 creates/inserts database data in a child script; L123–145 builds and prints a synthetic document, called at L221. Test33 also contains SQL mutations and synthetic PDF construction. | Fast or successful results are not valid GUI coverage. |
| Legitimate opaque editors could not receive CLI text | Access tests31/32 L142/L139 and test33 L193 reject a focused surface lacking a writable UIA pattern. PowerPoint test34 L201 shows the same limitation. | Agents build private input helpers or abandon GUI actions. Test33 L324–339 adds a delayed hidden sender to fight focus theft. |
| Pending edits were mistaken for failed typing | Excel tests27/28/29/30 L88/L73/L82/L84 deliver text but read back an uncommitted empty value. Their later exploration spends minutes finding a commit route. | Retrying typing or clicking another cell can corrupt the edit; longer verification polling cannot commit it. |
| Window identity could be incorrect or stale | Edge test8 L489 reports Explorer as ownedProcessId; test9 repeatedly fails ownership checks. The code searched by Process.ProcessName after launcher exit, allowing an empty selector, then overwrote the actual window PID with the launcher's PID. | Wrong ownership, focus rejection, risky cleanup targeting, repeated discovery. |
| Discovery and process overhead accumulated | Recent Excel sessions expose 42–77 parseable direct CLI response envelopes but only roughly 78–238 seconds of summed backend command time across sessions lasting 16–28 minutes. Repeated source/help reads, shell calls, thinking, generation, execution, and repairs occupy the rest. | Saving milliseconds inside a click cannot remove most session time. |
| Artifact verification caused additional repair loops | Excel test28 L258–339 encounters an unsupported PDF layout and repeatedly fixes inline Python quoting. Access runs similarly work around the built-in PDF reader. | Late assertion failures trigger unnecessary full application reruns. |
| Several smaller generic defects amplified these problems | Test30 L99 reports a screenshot Save/GDI+ error; screenshot code did not create explicit output parents. Test34 L132 exposes the potato_cli versus potato-cli test path mismatch. Edge sessions show overlapping calls and DesktopBusy. | Unhelpful failures, broken validation, and retries against uncertain state. |

The screenshot error's exact external cause is not proven from its message alone; missing output-parent handling was independently present and is now covered by a live fixture. Likewise, shell wall time minus reported backend time includes tool scheduling/wrapping, not just PowerShell startup. The analyzer excludes multi-envelope outputs from that overhead statistic. No aggregate native-versus-framework speed claim is justified without matching policies, routes, assertions, environment, and successful coverage. Older experiments reinforce the same transport/discovery/repair pattern and are retained in the metrics.

## Implemented changes

### Input and window handling

- Added **GuiNavigation** as the default policy. It permits audited `press-key` Tab, ShiftTab, Enter, Escape, and arrows with checked foreground ownership. Enter/Escape are single actions. Application hotkeys, clipboard, and Shortcut clearing remain blocked by default. An explicitly selected **VisibleControls** policy remains strict.
- Added `type -TargetMode Focused` for a visibly focused opaque editor. It still checks application/owned-dialog focus, rejects explicit read-only state and embedded navigation characters, and records the target. It cannot silently clear or refocus. It never claims verification unless requested. Normal writable-field typing remains the default.
- Added `click -RelativeX/-RelativeY` for fractions inside a discovered element's current bounds. No application selectors, coordinates, or expected content were embedded in shared helpers.
- Extended existing coordinate drag into **selector-based drag-and-drop**. Source/target selectors and optional relative positions resolve before mouse-down; movement is smooth by default; finally always releases the button. Returned dispatch success is separate from verifying an actual drop.
- Preserved actual window ownership across launcher handoff, rejected unrelated/pre-existing launch candidates, refreshed replaced working windows by PID, and cleared old working state after a new launch. Owned modal ancestry can establish cross-process input ownership without trusting an executable name alone.

### Workflow and time reduction

- Added `Invoke-Exploration.ps1` and the shared exploration checkpoint. Every CSV row must have performed GUI actions, a successful observation receipt, a route, and an observed expected result before development. The manifest binds the CSV, policy, coverage, and transcript hash. Completion also checks for still-visible windows belonging to recorded launches. Runtime initialization requires the completed manifest, including when standalone preflight is omitted.
- Added **receipt-producing sequential exploration batches** of up to 20 already-known commands. Each command retains its own result and receipt; failures and unmet waits stop the batch. This avoids repeated shell startup/tool calls without guessing unknown UI transitions.
- Preserved in-process generated execution and API exploration. The raw CLI stream now stops on failures/unmet waits by default. UI commands remain sequential.
- Pushed exact ControlType filtering into UIA while retaining localized-name matching, used provider FindFirst when the complete selector can be represented, and stopped client-side result inspection at MaxResults.
- Documented the distinction between typing and committing, closing a document versus exiting its application, and required routes versus permitted navigation. This directly addresses repeated edit and relaunch failures.
- Added an optional shipped **read-only pypdf fallback** selected through PythonPath or POTATO_PDF_PYTHON. It uses a script file rather than inline Python quoting and records which reader was used. Builtin-only remains dependency-free; nothing is installed automatically.
- Screenshot capture creates output parent directories and disposes resources on failures. Framework launch/test paths now resolve the actual potato-cli directory, retaining the legacy module-path fallback.

### Integrity checks

Preflight and runtime caller audits reject the observed COM, private native-input, SQL mutation, and synthetic-print/PDF patterns. Pure read-only artifact assertions and SQL text typed through the CLI remain allowed. API finalization with execution enabled requires a passing result for the current script hash, not an older revision. Mock authoring reports incomplete exploration and does not fabricate coverage.

These are workflow/audit checks, **not a security sandbox or a semantic proof**. An unrestricted agent could forge evidence or use another unrecognized mechanism; code review and honest observation still matter. The results now state the scope of policy assessment. No expected output is generated by the new CLI/framework helpers.

## Validation and timing

`verification.json` records the full final test run. Tests cover policy boundaries, wrong-process/unfocused/read-only rejection, relative geometry, launched-window identity checks, missing/altered exploration evidence, batch failure stopping, runtime rejection before COM activation, and API refusal of missing/stale execution evidence.

The live WinForms fixture verifies literal Unicode text, an actual opaque control without a writable UIA pattern, Tab/ShiftTab focus changes, relative clicks, screenshot parent creation, an actual drag/drop payload, modal discovery, and scoped cleanup. A separate simulated movement failure confirms button release. PDF tests cover quoted paths, reader provenance, unsupported builtin layouts, and invalid input. No supplied Office/browser test script was executed.

| Local measurement | Separate processes | Reused process/batch |
|---|---:|---:|
| Five identical exploration help commands, each with a receipt | 3,430 ms | 795 ms |
| Ten identical existing-file waits through generated runtime | 7,244 ms | 566 ms |

The first comparison measures the newly added batch path: about **77% less local elapsed overhead** for that small workload. The second confirms why the already-existing InProcess default should be retained; it is not a new improvement introduced here. These microbenchmarks do not predict end-to-end savings. The next controlled runs should keep CSVs/environment constant and record the chosen policy; GuiNavigation and historical VisibleControls runs are different conditions.

Individual UIA provider calls can still exceed retry timeouts. Broader process supervision remains a limitation. Full Office/browser reruns are needed to measure session-time improvement and provider-specific reliability; generic fixtures demonstrate the new primitives, not universal application compatibility.

## Using the update

Start with `automated-gui-testing-agent-framework/docs/AUTHORING.md`. Finish the full exploration in its own run folder, then pass its `logs/exploration.json` through `-ExplorationPath` when executing under a fresh RunRoot. Old generated scripts without that evidence must be re-explored; they do not silently retain compliant status. Explicit strict runs select `-InteractionPolicy VisibleControls` consistently throughout.

The source changes are local in the CLI and framework repositories. The original supplied result logs/scripts and the existing distribution ZIPs remain unchanged. Updated distribution archives and a pre-change backup are under `C:\diplomamunka\outputs`.
