# Session review, round 6

The previous batch/input/content changes worked: exploration is about one third shorter, request-file creation calls disappeared, and the generated script now reads and checks the reopened document's content. The remaining time is increasingly spent repairing runtime mismatches rather than discovering the GUI. This patch addresses those mismatches without application-specific selectors or shortcuts.

## Supplied-run measurements

| Phase | Previous run | Latest run |
| --- | ---: | ---: |
| Preparation | 73.026 s | 63.648 s |
| Full GUI exploration and checkpoint | 606.221 s | 402.457 s |
| Generation and first preflight | 107.749 s | 132.870 s |
| Execution, diagnosis and repairs | 231.003 s | 300.888 s |
| Delivery | 14.055 s | 6.438 s |
| Total | 1032.054 s | 906.301 s |

Total elapsed time improved **12.18%**, from 17m12s to 15m06s. Exploration improved **33.61%**, from 10m06s to 6m42s. Tool calls fell from **90 to 62**, and request-file creation calls from **23 to zero**. The latest session used stdin batches and combined help successfully. There were no failed direct CLI command envelopes during exploration, although recording a valid window observation failed at the framework layer.

The final supplied script reported **28.129 seconds** total runtime, versus 32.530 seconds in the previous supplied run. Its 34.5-second shell call includes startup/reporting. Wrapper overhead was only 0.633 seconds; trimming the wrapper further is not the main opportunity. Four full generated executions were needed, up from three. Repair time rose by about 70 seconds.

These measurements describe the supplied sessions before this patch. `analyze_word.py` and `metrics.json` preserve source timestamps, phase boundaries, failures, screenshot dimensions and timing fields. Overlapping shell durations are not summed as elapsed time. Direct CLI backend totals exclude commands nested inside generated execution results.

## Findings and implemented fixes

Original rollout line numbers identify tool calls and their following outputs.

**1. DPI settings changed the coordinate system between calls.** The screenshot at line 61 reported 1920×900, while the screenshot at line 120 reported 1536×720. The failure images at lines 209 and 272 were again 1920×900. Meanwhile, UIA bounds described a 1920-pixel desktop. The agent reused a point that worked during exploration, then had to repair it after the third generated execution. The dimension inconsistency is direct evidence; its contribution to that exact missed click is an inference, since application layout can also change.

This mismatch was reproduced locally: under an unaware caller, WinForms cached a width of 1536 for a 1920-pixel physical display. The CLI now establishes per-monitor DPI awareness for each desktop command and restores the caller's thread context in `finally`, including failures. Screenshot bounds come from native metrics under that context rather than WinForms' cached scaled bounds. Screenshot output identifies physical coordinates, pixel dimensions and region origin. The implementation follows Microsoft's distinction between [physical UIA coordinates and logical coordinates](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-screenscaling) and the reversible [thread DPI context API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext).

**2. Scoped window searches omitted the scope root.** The first generated execution, line 203, waited 15 seconds for a Save As Window inside `Scope FocusedWindow`. The dialog was already the root, but the search examined descendants only. `select`/`wait-element` now include the owned foreground root when the query explicitly targets a Window or WindowTitle. They still cannot escape into the parent app or another application. The real GUI fixture verifies both cases. Ordinary control queries retain descendant semantics.

**3. Relative context paths reached a GUI filename field.** The second generated execution, line 238, waited 30 seconds for a file that was never saved to the intended run folder. The agent had derived its filename from a relative `Context.ExecutionEvidenceRoot`. Runtime initialization now resolves run, evidence, log, CLI, CSV and manifest paths using the PowerShell current location. This matters because the .NET process current directory can differ. The template builds filenames from the absolute context, and a regression test changes PowerShell location before passing relative paths.

**4. The evidence gate rejected a useful window observation.** At line 150, RecordSteps rejected a successful `windows` result proving the changed window title. Replacing the receipt and rereading status took another interaction cycle. Nonempty `windows` results are now eligible, while empty ones remain rejected. Responses expose `verification.eligible` and a reason for ineligible receipts. A row can retain several `verificationCommandIds`, such as file existence plus saved window title; every receipt is validated against the same row. Singular IDs and existing manifests remain supported. This does not claim that a window title proves document contents.

**5. Bounded discovery was mistaken for proof of UIA absence.** At line 114 the agent queried exact labels and observed only to depth six, then concluded that the visible File control was unavailable. An accessible label can include extra words, and deeper descendants had not been inspected. Compact observations now report `depthBoundaryReached` separately from exhaustion of the node budget. The response and guide recommend one targeted deeper subtree or visible-label fragment query before a coordinate fallback. No extra tree traversal is performed merely to compute this flag; reaching the boundary indicates uninspected descendants, not a claim that descendants exist.

At line 120 the agent also captured a screenshot and clicked a newly chosen point in the same batch, before viewing the image. The only image-view calls in this rollout were later failure diagnosis. Guidance now explicitly separates screenshot inspection from choosing a new fallback point. Screenshot metadata cannot mechanically prove the agent inspected an image, and no fake “visual confirmation” gate was added.

**6. Cleanup could report stale window state.** The first two failing runs reported cleanup failure, but subsequent close commands found no matching window. Inspection found a concrete race: after a positive window snapshot, an exited process caused the loop to break without updating that snapshot. The final close could also finish while the deadline expired. Cleanup now checks the original PID/start-time identity and takes a fresh final observation before declaring remaining windows. Reused PIDs are never closed. Tests cover genuine remaining windows, exit between observations, and PID reuse. The code defect is reproduced by these tests; the supplied log does not identify which exact race occurred during those particular exits.

**7. Diagnosis repeated work already available in results.** There were three redundant standalone preflights after repairs, extra process/window checks, and source reads despite combined helper help. The result now places `summary.failedSteps` and `cleanupOk` before the long transcript. Guidance directs recovery from those fields, preserves tested transition guards, and avoids a separate preflight before a script that already preflights itself. Failed cleanup still requires recovery; its status is not ignored to save time.

## Verification and compatibility

Ten suites passed under Windows PowerShell 5.1. With the targeted cleanup follow-up, the total is **238 checks plus the real GUI smoke fixture**. See `verification.json` and `followup-verification.json`.

- DPI tests exercise unaware and system-aware callers, cached screen bounds, actual image dimensions and restoration after success/failure. Local result: physical 1920×1080, unaware cached width 1536.
- Real GUI tests exercise dialog-root waits, rejection of a parent outside that scope, depth-boundary metadata, Unicode and focused typing, duplicate-label handling, mouse positioning, actual drag/drop payload and owned closure.
- Framework tests cover absolute paths under a changed PowerShell location, valid/empty window receipts, multiple receipts and invalid secondary IDs, existing evidence gates, cleanup races and retained failure semantics.
- Both repositories pass `git diff --check`. The supplied files were read-only inputs; neither was executed or edited.

Desktop DPI handling requires Windows 10 version 1607 or later. **Old absolute coordinates recorded under DPI virtualization must be rediscovered.** Physical pixels align the transports; they do not make a hardcoded point portable across different layouts, resolutions or app versions. Prefer observed selectors and element-relative clicks. Reopen/content checks, full exploration, GUI-only policy and ownership restrictions remain in place. No application-specific helper, COM/clipboard route, fabricated output, or process-name force-kill was introduced. Existing click/drag/drop functionality remains tested.

This patch has not been measured in a fresh complete Office authoring session. The fixture results establish the listed fixes, not a promised number of minutes saved in the next run.

Updated sources are in the two repositories, with packages at:

- `C:\diplomamunka\outputs\potato-cli-improved-20260930-round6.zip`
- `C:\diplomamunka\outputs\automated-gui-testing-agent-framework-improved-20260930-round6.zip`

`package-manifest.json` records archive and file hashes. Packages exclude Git history, session state and run artifacts. No commit or PR was created.

Input SHA-256:

- Rollout: `472e457c8c19751026c6740dddab7d0b5c20f468fc389dfefa30e6bc3565dfb8`
- Script: `d4005159293dc47d26d229fa8b274c473e2255fd247c84cef5257ca552fe77d5`
