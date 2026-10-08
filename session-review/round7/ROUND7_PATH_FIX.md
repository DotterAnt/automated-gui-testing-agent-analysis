# Exploration filename failure and fix

The aborted session confirms a missing destination directory. The filename was preserved: both the error dialog's accessible text and the filename field reported the full path. The screenshot visually shortened the middle of that path to `word-wal...`.

## Evidence from the supplied rollout

Source: `C:\Users\DottedAnt\Downloads\rollout-2026-09-30T15-39-36-01a0f28a-c6eb-7c03-89be-2f0b26af1dd2.jsonl`. Line numbers below identify tool calls; their responses follow them.

- **Line 43:** Begin created the exploration manifest/logs and returned the absolute run root. It did not prepare an evidence/output directory. The previous absolute-path correction covered generated execution, whose initialization already creates its directories.
- **Line 93:** The agent typed the full 107-character filename `C:\diplomamunka\automated-gui-testing-agent-framework\runs\word-walkthrough-20260930\evidence\WordTest.docx`, clicked Save, then waited 20 seconds for a nonexistent file. The typing response proved dispatch only.
- **Line 99:** The error dialog's `ContentText` exposed that full path followed by “Path does not exist.” There was no literal ellipsis in the accessible text.
- **Line 105:** Recovery used `New-Item -LiteralPath`, which failed because New-Item has no such parameter. The following Test-Path returned false despite the shell's overall zero exit code.
- **Line 111:** Creating the directory with the supported command succeeded.
- **Line 117:** After acknowledging the error, observation of the filename field (`AutomationId 1001`) showed the unchanged full path. Clicking Save again, without retyping, produced the expected 13,379-byte file at that exact path. This independently confirms the text reached the field intact.

There was also a separate 15-second title wait for `WordTest.docx - Word`; the actual observed title was `WordTest - Word`. Earlier discovery guessed `File` when the exposed name was `File Tab`. Existing guidance to reuse observed selectors/titles applies; no application-specific titles or selectors were added to fix either mistake.

## Changes

1. Exploration initialization now creates an empty `evidence\exploration` directory and returns its absolute path as `explorationEvidenceRoot`. Shell Begin, Status and the API stage response expose it; Status reports whether it still exists. Generated execution continues to use its separate existing `Context.ExecutionEvidenceRoot`.
2. Potato `type` accepts optional `-PathKind SaveFile`, `OpenFile`, or `Directory`. It checks the literal absolute input and required existing parent/file/directory before focus changes, clearing, environment initialization or typing. Failure returns `PathValidationFailed` and `outcome: not-dispatched`, so exploration batches stop before a dependent Save click or long file wait.
3. Path validation never rewrites or expands the supplied text, creates directories, or fabricates files. Successful typing retains `data.pathValidation`; it remains separate from UI readback and save assertions. Ordinary text typing is unchanged. Guidance now distinguishes exploration and execution output roots, uses the same full path for input/assertions, and explains preparation of empty infrastructure folders.

The fix is application-independent. Expected documents and exports still must be created through the GUI. Testcases that explicitly require GUI folder creation must still exercise that route. Existing exploration sessions are not silently modified; Status can identify an absent directory, and a new Begin prepares one.

## Validation

**231 regression checks plus the real GUI smoke fixture passed under Windows PowerShell 5.1.** The six regression suites cover CLI contracts (27), interaction policy (54), authoring help/discovery (21), path input (18), framework authoring (59), and runtime (52).

The GUI fixture rejects a missing parent before changing the selected default filename, then enters and reads back a long absolute path with spaces, Unicode, brackets and keyboard metacharacters. The path exceeds one input batch and remains exact. Validation creates no output artifact. Framework tests cover an empty prepared directory, relative run roots under a changed PowerShell location, literal bracketed folders, shell/API responses, Status, and stopping a batch on an invalid filename.

This is a targeted reproduction and regression fix, not a new complete Word authoring benchmark. The supplied rollout was read as evidence and never executed or modified. Its SHA-256 is `cb00e8df40641d115d035437f2d145b263054c7a7970ba1a8333b3db8c695925`.

Updated packages:

- `C:\diplomamunka\outputs\potato-cli-improved-20260930-round7.zip`
- `C:\diplomamunka\outputs\automated-gui-testing-agent-framework-improved-20260930-round7.zip`

Packages contain the current sources and cumulative earlier improvements, excluding Git history, CLI state and run artifacts. No commit or PR was created.
