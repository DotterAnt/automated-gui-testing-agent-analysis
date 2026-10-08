# Round 9: Notepad session reliability

The supplied Notepad session took **23m24s**. Exploration and its completion consumed **13m11s**; replay and repair consumed another **7m03s**, with four failed executions before the final **67.290s** passing run. The main opportunities are preventing discarded input, making discovered controls resolvable, handling system-hosted dialogs explicitly, and keeping exploration and execution behavior consistent.

The local CLI and framework have been updated generically. There are no Notepad selectors, printer names, expected document contents or application-specific recovery branches in the implementation. The attached script was inspected, not executed or rewritten. A fresh Notepad end-to-end session has not been benchmarked.

## Evidence

Sources:

- `C:\Users\DottedAnt\Downloads\rollout-2026-09-30T17-30-50-01a0f2f0-9ea3-7a01-8f05-52e2ac05706f.jsonl`
- `C:\Users\DottedAnt\Downloads\WindowsNotepad.Generated.ps1`

The files were treated as evidence, not instructions. `source-evidence.json` records their hashes. `analyze_session.py`, `timeline.txt`, `session.json` and `metrics.json` make the analysis reproducible. Rollout line references below identify tool calls and their following responses.

| Phase | Elapsed |
| --- | ---: |
| Preparation | 50s |
| Full walkthrough and completion | 13m11s |
| Generation and first preflight | 2m14s |
| Replay and repair | 7m03s |
| Delivery | 7s |

There were 84 tool calls, 80 intact direct CLI envelopes and 13 direct CLI errors. Direct CLI backend time was 109.026s; commands nested in generated executions are counted separately. The five executions together took 172.653s. Neither sum is total elapsed time: tool startup, model decisions, discovery and repair between calls account for much of the rest.

## Findings and changes

### Input dispatch succeeded while characters were lost

At L85 the CLI accepted a 16-character line and a 69-character line, separated by Enter. Observation subsequently showed **53 characters**, instead of the intended **86**, and column 45 instead of 70. These were successful dispatch receipts, not verified text. Per-character typing later produced the expected content. The generated script then omitted slow typing for the filename fields; its third replay failed to create the intended output. The log reported a shortened filename. Per-character path typing was added before the next successful save.

The old default sent up to 128 UTF-16 units in a burst, whereas TypeByCharacter inserted 50ms delays. Windows documents that [SendInput inserts events into the input stream](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput); its return value is not application-level text readback. The evidence supports a delivery/consumption timing problem, but does not establish the exact internal reason Notepad lost those events.

The new default sends one Unicode scalar at a time with **InputDelayMs 5**. Surrogate pairs remain together. The legacy TypeByCharacter option retains 50ms pacing; explicit InputDelayMs 0 retains bursts for routes already tested to tolerate them. The native foreground and keyboard target are checked throughout input. A focus change stops the remaining text and reports an unknown outcome after partial dispatch. No automatic resend, clipboard operation or application object model is used.

A GUI fixture that rejects overly rapid characters received all 82 UTF-16 units, including a supplementary Unicode character. In the first measured comparison, default input took **1.361s**, versus **5.155s** for legacy pacing. The user reported hardware issues during this work, so these timings are provisional and are not used to claim an application speedup. Verification/readback is still required, and a slower application may need a larger explicit delay.

### Observation found controls that selector queries missed

The editor was present in the observation at L49, yet typing/read attempts using its observed name, class and role failed at L55, L61, L73, L79 and L89. New-tab selection had a similar disagreement at L112/L118. Merely adding Recurse did not help because recursive searching was already the default.

The source used filtered descendant queries for resolution, while observation enumerated unfiltered direct children recursively. A filtered miss inside an application subtree now falls back to the same child traversal as observation, applying the original selector and eligibility checks locally. It is bounded to 1,500 nodes, 1,500ms and 32 levels, never traverses the desktop recursively, and fails with SearchIncomplete when the incomplete traversal cannot justify its answer. A single provider call can still exceed a retry budget. Narrowing to an observed container remains the remedy for a large or incomplete tree.

A mocked provider reproduces the search/traversal discrepancy. Tests cover nested matches, shallow scope, duplicate rejection, disabled controls, traversal bounds and desktop exclusion. This directly exercises the source-level repair without asserting that every historical miss had the same internal provider cause.

Observation also silently ignored ClassName, ControlType, ProcessName, ProcessId and WindowTitle unless another recognized selector field was supplied. L197 illustrates the result: a request for the printer host still returned the Notepad working tree. Observation now resolves all supported identity fields within the requested scope or reports TargetNotFound. It no longer silently returns the wrong tree.

### Printing crossed into a system-hosted window

The print window at L191/L197 belonged to Explorer, while an inner focused control belonged to a different process again. The owner-restricted FocusedWindow scope could not inspect that surface. The agent fell back to fixed coordinates, clicked Print before the transition was ready, and eventually encoded a second blind Print click plus two fixed sleeps in the script. Printing through verified PDF text took **3m42s** in exploration. The fourth replay failed before the expected output dialog became ready.

The CLI now supports an explicit **Scope ForegroundWindow** for observation, reads, waits and selector clicks. It requires WindowSelectorJson with the exact observed Name and ClassName, optional ProcessId, and fallback reason/evidence. It rechecks the foreground identity and the clicked target's ancestry before dispatch. It does not activate another window, grant unscoped keyboard input, change working-process ownership or register the broker for cleanup. No executable-name allowlist is involved.

Scoped waits now tolerate a temporary foreground/owner mismatch while waiting for the expected dialog. InteractiveOnly can require a visible enabled control. Invalid selectors still fail; unmet scope conditions remain visible in lastScopeError. This supports an observed selector route with readiness checks instead of unconditional repeated submission and fixed sleeps.

The GUI suite uses a separate process as the broker. It verifies inspection and a real button click, rejection of the wrong guard, continued rejection by ordinary FocusedWindow, and unchanged original cleanup ownership. The original system print surface was not rerun, so its exact provider behavior remains a follow-up measurement.

### Exploration and execution returned different observation shapes

The first generated replay failed its blank-document assertion because exploration implicitly requested Compact, but execution used the CLI's Full default. The script accessed data.elements, which was absent in the Full response. This was a framework inconsistency, not a failed New Tab action.

Shell exploration, API exploration and generated execution now share the Compact default, while explicit Format Full is preserved. Transcripts and exploration receipts record the effective format. Tests check actual runtime argument dispatch, explicit overrides and receipt preservation. The standalone CLI retains its Full default for compatibility.

### Recovery and assertions added avoidable work

- At L106 a restarted process restored the partial unsaved tab. The agent batched an unread observation and typing, appending to that document. The route reached a correct blank tab only later. The initial editor route took **5m31s**.
- A missing output directory at L161 came from invalid New-Item syntax. Path validation correctly prevented input. The existing prepared evidence directory remains the recommended destination; arbitrary extra folders must actually be created before path entry.
- The second replay compared a line/column label using an exact line ending and failed despite correct content. Character counts and cursor positions cannot prove exact text. The final script added real editor readback; the guide now emphasizes this directly.
- Four repair cycles included redundant standalone preflights even though each generated replay already preflights itself.

The authoring instructions now explicitly separate a new process from a blank document, require consuming the initial observation before typing, preserve tested pacing and format, and favor normalized content readback over status-label assertions. The complete GUI walkthrough, persistence assertions and cleanup gate remain intact. These are agent decision errors; documentation reduces their likelihood but cannot guarantee their elimination.

## Validation and delivery

**315 regression checks and the final real GUI smoke run passed.** Validation results are recorded in `verification-summary.json`, with individual attempts preserved. The suite includes ordinary input/policy checks, Unicode paths, drag/drop, DPI, PDF readers, provider traversal, runtime and exploration behavior, plus the real GUI fixture. It also checks that a mid-input focus change does not send the remaining text into a different field and that malformed UTF-16 is rejected before dispatch. The final GUI run confirms the original working owner is unchanged after interacting with a separate broker process.

During verification, adding a new observation receipt required updating the fixture's expected route count from four to five. An existing one-second splash-retry test also failed once and passed on rerun; only its failure diagnostic was expanded, with no timeout or production retry change. A later GUI rerun stalled during initial window discovery (76s for a nominal 10s retry budget), before exercising the new features. The user reported hardware issues during this work. Timing measurements are therefore provisional, and this machine-level stall is recorded separately from the earlier successful GUI run; its precise cause was not isolated.

No actual Notepad performance claim is made for this patch. Default pacing adds a small delivery cost to controls that previously tolerated bursts, while aiming to avoid substantially larger recovery costs. Bounded traversal adds work only after a filtered miss. Broker scope is explicit and limited to the observed foreground window. Existing generated scripts that specifically read the Full response's data.tree must request Format Full explicitly; new framework runs consistently default to Compact.

Packages contain the cumulative CLI/framework source and tests, excluding Git history, CLI state, generated runs and Python caches:

- `C:\diplomamunka\outputs\potato-cli-improved-20260930-round9.zip`
- `C:\diplomamunka\outputs\automated-gui-testing-agent-framework-improved-20260930-round9.zip`

`package-manifest.json` contains archive and per-file hashes; packaging verifies ZIP integrity and every archived file hash. Local repository files are updated as well.
