# Word session review, round 5

The supplied run improved overall, but exploration got longer. The strongest remaining opportunities are reducing agent/tool round trips, preventing ambiguous GUI actions, and making valid verification easier. The final script's transport is already inexpensive, so weakening waits or skipping exploration would target the wrong problem.

## Measured supplied-run results

| Phase | Previous supplied run | Latest supplied run |
| --- | ---: | ---: |
| Preparation | 145.310 s | 73.026 s |
| GUI walkthrough and checkpoint | 533.744 s | 606.221 s |
| Generation and first preflight | 154.382 s | 107.749 s |
| Execution, diagnosis, repairs | 334.703 s | 231.003 s |
| Delivery | 38.556 s | 14.055 s |
| Total | 1206.695 s | 1032.054 s |

Overall elapsed time fell **14.47%**, from 20m07s to 17m12s. Exploration rose by 72.477 seconds. Generated executions fell from four to three. The final runtime reported **32.530 seconds**, including 31.109 seconds inside CLI commands and just 0.567 seconds of wrapper overhead. Its shell call took 39.4 seconds; these are different timing boundaries. The previous run exposed only a 35.2-second final shell duration, so these data do not establish a faster latest replay.

There were 90 tool calls: 61 shell calls and 29 patches. **23 patches created individual batch request JSON files**, followed by separate execution calls. Direct CLI output contained 56 intact envelopes totalling 75.069 backend seconds. That subtotal excludes generated-script command records and must not be treated as the complete session's tool time. Discovery improved from 30 selects, including 18 misses, to four selects and one miss; observations increased from 13 to 18. Compact output helped, but it did not eliminate repeated decisions and tool calls.

`analyze_word.py`, `session.json`, `timeline.txt` and `metrics.json` make these measurements reproducible. Phase boundaries use source timestamps rather than adding overlapping shell durations.

## Causes and changes

Source line numbers below refer to the original attached JSONL; they are tool call locations, with their corresponding outputs immediately afterwards.

1. **A file-edit round trip before almost every batch.** Calls at lines 55–315 created 23 `request-NN` files. The previous documentation encouraged this. `Invoke-Exploration.ps1` now accepts `-RequestsStdin` for both Batch and RecordSteps. The documented UTF-8 literal here-string combines request construction and execution in one shell tool call. Existing file requests still work; every executed command still gets a receipt, and the entire batch is validated before dispatch. This can remove those 23 file-edit calls without removing any GUI step. It is a structural reduction, not a prediction of seconds saved.

2. **Unknown help topics hid useful help.** At lines 34 and 223, `pdf` and `read-text` caused combined help to discard valid topics, including `read`. The process also exited successfully despite `ok:false`. Valid topics are now retained alongside unknown/available topic lists, and the CLI entrypoint exits 1 on failure. `Get-RuntimeHelp.ps1 -Names ...` also returns multiple signatures in one process, replacing the four separate helper lookups at lines 325–328.

3. **Identical labels resolved to the wrong control.** At line 168, `Close` selected the application window button instead of the Backstage document-close item, causing a restart. At line 269, `Print` selected the navigation item rather than the print submit button. Click now requires a single visible enabled match by default, including JSON selectors and path segments. It returns `AmbiguousTarget`, candidate metadata and `outcome:not-dispatched` before changing focus or sending input. Compact observations include class names, add observed role/class constraints for distinguishable duplicate candidates, and flag unresolved ambiguity. Editable selectors avoid mutable content names when an ID is available. No application labels or IDs are built into these rules.

4. **Focus/readiness repairs destroyed filename selection.** The first generated execution typed before the Save dialog's focus was ready. The next repair clicked the filename field, apparently losing its selected default and appending the path; the expected file wait then expired. `type -TargetMode Focused -ExpectedFocusJson ... -FocusTimeoutMs ...` now waits for an observed identity and owned foreground focus without clicking/refocusing. Existing selection is preserved, and the established ownership, read-only, literal input and fallback-evidence checks remain. Writable `-PreDelete -Verify` remains the preferred replacement route. FocusedWindow element waits also refresh the foreground scope after a failed lookup instead of retrying a stale root.

5. **Verified typing was wrongly rejected as an exploration receipt.** At line 89, typing successfully read back the expected text. RecordSteps rejected that receipt at line 299 solely because its command was `type`. The agent substituted a generic tree observation, weakening the link to actual content. Recording and execution validation now accept successful typing only when it contains actual successful verification metadata. Unverified typing still cannot satisfy the checkpoint. Guidance also surfaces the multiline Document requirement that caused the rejected Edit-target attempt at line 79.

6. **Reopen content was never actually asserted.** At line 229 and in the supplied final script, reopening only checked that a document named `WordTest` existed. The earlier failed `read-text` help lookup contributed to this omission. The later PDF content assertion is useful but does not prove that row's reopen expectation at the requested point. CLI `read` now reports `textSource`; the new general `Assert-TextContains` helper checks every supplied fragment using actual ValuePattern/TextPattern or read-pdf content and rejects accessible-name fallback. Authoring instructions explicitly require this check after GUI reopen. This improves available checks and guidance; arbitrary natural-language CSV expectations still require the author's judgment.

7. **Cleanup recovery escaped the ownership rules.** At line 403, the agent issued process-name-wide CloseMainWindow/Stop-Process outside the generated script. The final script uses the framework cleanup, but that external recovery was not compliant. Guidance now calls out this exact class of bypass and points to recorded ownership and preserved CLI state for GUI recovery. No broad force-kill helper was added. The framework cannot sandbox an agent's independent shell commands.

## Compatibility and limits

- Click's uniqueness requirement is deliberate: previously successful ambiguous scripts may now fail clearly and need an observed role, class, ID or parent scope. `-RequireUnique false` retains explicit legacy first-match behavior; authoring guidance says to resolve ambiguity rather than disable the check. Bounded observation candidates do not guarantee global uniqueness; the live click lookup is authoritative.
- New `read.textSource` is additive. `Assert-TextContains` requires the updated CLI for GUI reads. Existing text assertions remain supported.
- `potato.ps1` now uses nonzero process exit for command failures, agreeing with its JSON. Callers that ignored JSON errors may now stop earlier.
- Complete exploration, policy enforcement, receipt preservation, failure-stop sequencing and owned cleanup remain required. Navigation/focused typing permissions are unchanged. No COM, clipboard, private input backend, document fabrication or application-specific helpers were added.
- Click/hold/drag/drop already exists and remains covered by both failure-release checks and a real GUI drop payload test.

## Verification and delivery

All nine suites passed under Windows PowerShell 5.1: **220 automated checks plus the real GUI smoke fixture**. The fixture verifies duplicate-label rejection before input, JSON/path uniqueness, successful disambiguation, unchanged text on a failed focus guard, selected filename replacement, real readback provenance, Unicode input, actual drag/drop payload, modal scope and owned closure. Regression tests cover UTF-8 stdin, invalid batch rejection before dispatch, failure-stop behavior, partial help and exit status, verified/unverified receipts, and missing-content/name-only assertion failures. After moving transient focus-provider errors inside the bounded retry, the affected 21-check suite was rerun and passed. See `verification.json` and `followup-verification.json`.

Both repositories pass `git diff --check`. Sources were updated in place and packaged under `C:\diplomamunka\outputs` as the two `*-improved-20260930-round5.zip` archives. `package-manifest.json` records archive/file hashes. Archives exclude Git metadata, runtime state and run artifacts. No commit or PR was created.

This patch was verified with application-independent fixtures, **not a new complete Office authoring session**. A fresh run is needed to measure authoring-time savings and find remaining provider-specific problems. The supplied script and rollout were analyzed read-only and left unchanged.

Input SHA-256 values:

- Rollout: `e774d7b69e57e6ab5e9ad54d4d52d1ccfcb3483995fc4af19d127f25e5f01827`
- Script: `346c8117604217e84f810c831349eca361fc73daF3f1e8e2a7efdd6c6a74ebf9` (case-insensitive hex)

Automatic approval review rejected removal of the diagnostic folder `C:\Users\DottedAnt\AppData\Local\Temp\agta-stdin-probe-40f52c77-65d2-424c-a143-ab926f77a977` with only “blocked by policy” as its reason. That small temporary folder was left in place; repository verification and packaging were unaffected.
