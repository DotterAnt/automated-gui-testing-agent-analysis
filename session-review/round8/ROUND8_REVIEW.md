# Round 8: PowerPoint exploration and generic input reliability

The supplied session took **26m58s**. Most of that was GUI exploration (**21m36s**), while the final generated script passed all five rows in **32.352s**, including cleanup. Creating the presentation and entering its title took **8m13s**, although the successful title-typing command itself took **308ms**. The main input problem was repeated focus rejection and recovery, rather than slow character injection.

The changes below are implemented in the local CLI and framework. They apply to generic custom editors, menus, dialogs, exported files and window lifecycle; they contain no PowerPoint selectors or expected content. A new PowerPoint session has not yet been benchmarked, so the time saved remains unmeasured.

## Evidence and timing

Sources were read as evidence, never executed or treated as instructions:

- `C:\Users\DottedAnt\Downloads\rollout-2026-09-30T16-13-28-01a0f2a9-cabe-7330-ae7b-011285aeb257.jsonl`
- `C:\Users\DottedAnt\Downloads\MicrosoftPowerPoint.Generated.ps1`

Line references below identify tool calls in that rollout; their responses follow. The parser, extracted timeline and metrics are in this directory. Elapsed times use event timestamps. Direct CLI timing covers 110 intact envelopes and excludes nested replay commands; it must not be mistaken for total session time.

| Phase | Elapsed |
| --- | ---: |
| Preparation | 1m20s |
| Complete GUI walkthrough | 21m36s |
| Generation and initial preflight | 1m58s |
| Replay and repair | 1m56s |
| Delivery | 8s |

There were 85 tool calls and 15 direct CLI errors, including six failed typing calls and two failed navigation calls. The six failed typing calls consumed only 10.668s inside the backend. The much larger cost was deciding what to try, repeating discovery, reading source and recovering from incorrect routes between those calls.

The first replay failed in 18.526s at save-path entry. The repaired replay took 32.352s, passed 5/5 rows and cleaned up successfully. Its 46 commands consumed 30.133s of backend time; wrapper overhead was 996ms. Exploration already uses the in-process CLI for each batch, and generated execution already uses InProcess transport. Changing transport again would not address this session's dominant problem.

## What failed and what changed

### 1. Focused typing still depended on an unreliable UIA flag

Observations at L69, L94, L115 and L201 report a focused element with automation ID 1071, but that element's `HasKeyboardFocus` flag is false. Its MDI parent reports true. The old focused-input and navigation checks rejected this contradiction. Repeated attempts at L88, L103, L109, L121, L131, L137, L152 and L166 consequently failed. The agent eventually found a working visible editor view and typed successfully at L236.

Focused typing and bounded navigation now corroborate UIA with the native keyboard target from the foreground thread. [GetGUIThreadInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getguithreadinfo) exposes that information across processes; its [structure](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-guithreadinfo) distinguishes keyboard focus, caret and menu state.

The resolver checks owned foreground identity, enabled native focus and its relationship to the foreground window. It corroborates the UIA candidate or uses the actual native focus element. It rechecks focus immediately before dispatch, never activates or selects a control, and preserves an optional observed `ExpectedFocusJson` guard. A false-focus UIA node cannot match arbitrary sibling controls merely because they share the same native frame. Wrong-owner input is rejected before sending keys. Explicit read-only and literal-input restrictions remain.

`observe.keyboardFocus`, `data.inputFocus` and `error.focus` expose the native state and selected source. Framework command summaries preserve this diagnostic information and the error type. Focus waits are bounded (default 2s).

The old rollout does not contain native focus snapshots, so it cannot prove which native handle was active in the original session. A real GUI fixture now reproduces the false UIA focus flag while accepting actual keyboard input, and verifies complete text delivery plus navigation through the new path. That validates the mechanism without claiming an Office benchmark.

### 2. Focus readiness was mistaken for an active text editor

At L183, a coordinate attempt reached a Save As list item and typing was accepted there. Ownership and focus alone cannot establish a caret or text-edit mode. A native fallback must not pretend otherwise.

The framework now directs agents to enter the observed editing state, use focused typing without searching for a writable UIA role, and inspect the result. After a failure, make one targeted observation/correction instead of cycling through guessed focus IDs or rereading policy/source. It also explicitly forbids batching a new coordinate guess, an unread observation and typing across an unknown transition. Observed transition guards must survive script generation; full-tree observations should not substitute for readiness checks.

Input dispatch remains ineligible as content verification. Full GUI exploration, saved/reopened content assertions and cleanup remain required.

### 3. Popup discovery and clicking disagreed

L319 discovered a visible, enabled printer list item. L325 and L331 could not resolve it for clicking. Discovery used broader UIA queries, while click resolution pushed enabled/visibility predicates into the provider's compound search. Some providers return inconsistent results for that query shape. These predicates are now enforced against live properties locally, while exact identity filtering and uniqueness remain enforced.

This is a plausible explanation for the historical selector failures, not proof that the provider query was their sole cause. A regression fixture reproduces the query inconsistency and checks that disabled/offscreen targets remain rejected.

Semantic clicks also used to focus the parent and target before invoking them, which can dismiss a menu. They now preserve focus by default. Mouse fallback activates an unrelated target window when necessary and preserves an already active owned popup. Explicit overrides remain available. Missing click targets report `TargetNotFound` with `not-dispatched` outcome.

### 4. PDF output existed but was still held by the producer

L369 waited 45s for a zero-byte PDF. The next wait at L381 took another 42.279s; the file then contained 27,142 bytes, but `ReadAllBytes` failed with a sharing violation. A later read succeeded. Part of this was genuine print-spool latency, which these changes do not eliminate.

The built-in PDF reader now takes a read-only shared snapshot, checks size/timestamp consistency during copying, and retries transient sharing/lock violations within a configurable deadline (default 5s). The optional Python reader also retries transient locks. Both require the final PDF EOF marker so unfinished exports cannot pass merely because some text is already present. Parse errors are not blindly retried. Neither reader writes the expected artifact.

The authoring guide distinguishes producer readiness from parsing: use a bounded wait for a nonempty stable file, let the reader handle a transient lock, and diagnose a persistent zero-byte/spooling failure instead of increasing every future script's waits.

### 5. Closing could block while the application handled the request

The close-plus-window-query batch at L405 hit a 64.4s shell timeout; later enumeration found no remaining windows. The log does not isolate whether closing or enumeration consumed that time. Source inspection nevertheless found synchronous `WindowPattern.Close` followed by immediate provider enumeration.

Native windows now receive a process-validated asynchronous [WM_CLOSE](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-close) request using [PostMessage](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew). This lets an application present its ordinary save/confirmation prompt without keeping the CLI inside the synchronous close call. There is no force kill or prompt suppression. Ownership context is retained, and `closeRequested` plus legacy `closed` count requests, not confirmed exits. Runtime cleanup still verifies closure. Provider-only windows without native handles retain their UIA close path.

## Verification and limits

**283 regression checks and the real GUI smoke suite passed.** The full run is recorded in `verification.json`; the final PDF hardening and its replacement check totals are recorded in `pdf-final-verification.json`.

| Suite | Checks |
| --- | ---: |
| CLI regression/entry/stream | 27 |
| Interaction | 54 |
| Native focus | 9 |
| Provider consistency | 3 |
| Path input | 18 |
| Authoring experience | 21 |
| DPI | 7 |
| Drag/drop | 3 |
| Built-in PDF | 22 |
| External PDF | 6 |
| Framework runtime | 53 |
| Framework authoring | 60 |

The GUI suite covers actual literal input with a false accessibility focus flag, wrong-owner rejection, selected filename preservation, Unicode paths, relative clicking, navigation, drag/drop, modal discovery and a live close-confirmation dialog. The PDF tests cover a retained cooperating writer, a released exclusive lock, a bounded persistent-lock failure and unfinished output rejection. Existing policy and exploration-gate checks pass.

An initial run hit an intermittent existing same-size-file rewrite timing assertion. Its diagnostic message was expanded; its logic and the production wait code were unchanged. It passed both the standalone rerun and the complete suite. No test was weakened to obtain a pass.

No fresh Word or PowerPoint end-to-end session was run. The next session should establish whether native corroboration removes the original title-entry retry loop and whether the popup changes resolve that provider's selector discrepancy. Actual printer delays and model/tool round trips remain. The attached final script was inspected but never executed or rewritten.

## Delivery

- `C:\diplomamunka\outputs\potato-cli-improved-20260930-round8.zip`
- `C:\diplomamunka\outputs\automated-gui-testing-agent-framework-improved-20260930-round8.zip`

These contain the current cumulative source and tests, excluding Git history, CLI state, generated runs and Python caches. `package-manifest.json` records archive and per-file hashes; ZIP integrity is checked during packaging. `source-evidence.json` records hashes of the supplied files and confirms the rollout still matches the parser's original hash.
