"""Read supplied session logs as data. Never execute logged code or test scripts."""
from __future__ import annotations

import collections
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import statistics

APPS = {"word": "Word", "excel": "Excel", "powerpoint": "PowerPoint",
        "access": "Access", "edge": "Edge", "notepad": "Notepad",
        "onenote": "OneNote", "paint": "Paint", "photos": "Photos",
        "snippingtool": "Snipping Tool"}
GROUPS = {"native": "Native (baseline)", "cli": "CLI + framework"}
PASS = {"pass", "passed", "success", "succeeded"}
FAIL = {"fail", "failed", "error"}


def stamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_records(path):
    # str.splitlines() ALSO splits U+0085 inside valid JSON strings containing
    # decoded binary/PDF data. Only LF delimits records in these JSONL files.
    records, errors = [], []
    for line, raw in enumerate(path.read_text(encoding="utf-8-sig").split("\n"), 1):
        if not raw.strip():
            continue
        try:
            records.append((line, json.loads(raw)))
        except ValueError as exc:
            errors.append({"line": line, "error": str(exc)})
    return records, errors


def body(output):
    return re.split(r"\r?\nOutput:\r?\n", output, maxsplit=1)[-1]


def json_values(text):
    decoder = json.JSONDecoder()
    consumed = -1
    for match in re.finditer(r"(?m)^[ \t]*[\[{]", text):
        start = match.end() - 1
        if start < consumed:
            continue
        try:
            value, count = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        consumed = start + count
        blocks = value.get('content') if isinstance(value, dict) else value
        if isinstance(blocks, list) and blocks and all(isinstance(b, dict) and b.get('type') in {'text', 'image', 'input_text', 'input_image'} for b in blocks):
            for block in blocks:
                if block.get('type') in {'text', 'input_text'}:
                    yield from json_values(block.get('text', ''))
        else:
            yield value


def json_field(text, name):
    """Recover a complete field from a truncated runtime JSON envelope."""
    match = re.search(r'"' + re.escape(name) + r'"\s*:\s*', text)
    if match:
        try:
            return json.JSONDecoder().raw_decode(text[match.end():])[0]
        except ValueError:
            pass
    return None


def execution_headers(text):
    """Recover replay headers without mixing adjacent command/result objects.

    A shell output can contain a successful CLI state command followed by a
    failed replay with truncated step detail. Its earlier command-level ok
    and interactionPolicy must not become the replay's metadata.
    """
    decoder = json.JSONDecoder()
    consumed = -1
    for match in re.finditer(r'(?m)^[ \t]*\{', text):
        start = match.end() - 1
        if start < consumed:
            continue
        fragment = text[start:]
        try:
            _, count = decoder.raw_decode(fragment)
            fragment = fragment[:count]
            consumed = start + count
        except ValueError:
            pass
        identity = json_field(fragment, 'executionId')
        summary = json_field(fragment, 'summary')
        if not identity or not isinstance(summary, dict):
            continue
        if json_field(fragment, 'runKind') == 'Diagnostic' or json_field(fragment, 'qualifying') is False:
            continue
        yield {key: json_field(fragment, key) for key in
               ('executionId', 'ok', 'summary', 'cleanupOk', 'interactionPolicy',
                'timing', 'startedAt', 'finishedAt')}


def lower_keys(value):
    return {str(k).lower(): v for k, v in value.items()}


def state(value):
    if value is True or str(value).lower() in PASS:
        return "PASS"
    if value is False or str(value).lower() in FAIL:
        return "FAIL"
    if str(value).lower() in {"skip", "skipped"}:
        return "SKIP"
    return None


def normalized(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def step_index(value, actions):
    if str(value).isdigit() and 1 <= int(value) <= len(actions):
        return int(value)
    for i, action in enumerate(actions, 1):
        if normalized(value) == normalized(action):
            return i
    return None


def parse_steps(value, actions):
    found = {}
    if isinstance(value, list):
        for item in value:
            found.update(parse_steps(item, actions))
    elif isinstance(value, dict):
        keys = lower_keys(value)
        if keys.get('qualifying') is False or keys.get('runkind') == 'Diagnostic':
            return found
        status = state(keys.get("status", keys.get("passed", keys.get("result"))))
        index = next((n for name in ("action", "stepindex", "step", "name", "stepname")
                      if (n := step_index(keys.get(name, ""), actions))), None)
        if status and index:
            found[index] = status
        for key, item in value.items():
            index = step_index(key, actions)
            if index and isinstance(item, dict):
                sub = lower_keys(item)
                result = state(sub.get("status", sub.get("passed")))
                if result:
                    found[index] = result
            if str(key).lower() in {"steps", "results", "stepresults"}:
                found.update(parse_steps(item, actions))
    return found


def observed_steps(text, actions):
    if json_field(text, 'runKind') == 'Diagnostic' or json_field(text, 'qualifying') is False:
        return {}
    found = {}
    for value in json_values(text):
        found.update(parse_steps(value, actions))
    summary = json_field(text, "summary")
    if isinstance(summary, dict) and summary.get("total") == len(actions) and summary.get("passed") == len(actions) and summary.get("failed") == 0:
        found.update({i: "PASS" for i in range(1, len(actions)+1)})
    # Console rows and result CSVs are accepted only from eligible runtime
    # outputs/result reads, never from source-code or testcase reads.
    for line in text.replace("\r", "").split("\n"):
        clean = line.lstrip()
        if len(line) > 2200 or clean.startswith(("{", "+", "-", "#")) or (clean.startswith("[") and not re.match(r"\[\d{2}:\d{2}:\d{2}\]",clean)):
            continue
        if re.search(r"(?:^|\s)(?:Results:\s*5\s*/\s*5\s+Passed|Passed steps:\s*5\s*/\s*5|All 5 steps (?:have )?(?:Passed|PASS))\b",line,re.I):
            found.update({i: "PASS" for i in range(1,len(actions)+1)})
        statuses = re.findall(r"\b(PASS(?:ED)?|FAIL(?:ED)?|SKIP(?:PED)?)\b", line, re.I)
        if not statuses:
            continue
        for i, action in enumerate(actions, 1):
            if re.search(r"(?<!\w)" + re.escape(action) + r"(?!\w)", line, re.I):
                # Choose the status nearest the action; error details can
                # contain another step name/status later in the same row.
                action_at = line.lower().find(action.lower())
                matches = list(re.finditer(r"\b(PASS(?:ED)?|FAIL(?:ED)?|SKIP(?:PED)?)\b", line, re.I))
                nearest = min(matches, key=lambda m: abs(m.start() - action_at))
                found[i] = state(nearest.group())
    return found


def first_attempt_steps(text, actions):
    """Valid step measurements do not turn a repaired session into a full pass."""
    found = {}
    def candidates(value):
        if isinstance(value, dict):
            yield value
            for key in ('firstAttemptSuccesses', 'attempts'):
                for item in value.get(key, []):
                    yield from candidates(item)
        elif isinstance(value, list):
            for item in value:
                yield from candidates(item)
    for value in (item for parsed in json_values(text) for item in candidates(parsed)):
        if isinstance(value, dict) and value.get('countsAsSuccessfulStep') is True and value.get('status') == 'FIRST_ATTEMPT_SUCCESS':
            index = step_index(value.get('stepIndex'), actions)
            if index:
                found[index] = 'PASS'
    return found


def testcase_from_outputs(outputs):
    def package(rows, line, note=None):
        canonical = json.dumps(rows, sort_keys=True, ensure_ascii=False)
        result = {"rows": rows, "line": line, "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                  "has_data": any(r.get("Data", "").strip() for r in rows)}
        if note:
            result['normalization_note'] = note
        return result
    for item in outputs:
        help_output = item.get('tool', '').endswith('agta_help')
        csv_read = re.search(r"Get-Content|Import-Csv|\btype\b", item["command"], re.I) and ".csv" in item["command"].lower()
        if not (csv_read or help_output):
            continue
        text = body(item["text"]).replace("\r", "")
        for value in json_values(text):
            if help_output and isinstance(value, dict):
                value = value.get('steps')
            if isinstance(value, list) and len(value) == 5 and all(isinstance(r, dict) and r.get("Action") and r.get("Expected Result") for r in value):
                return package(value, item["line"])
        lines = [line for line in text.split("\n") if line.strip()]
        for i, line in enumerate(lines):
            header = line.strip().lower().replace('"', '')
            if header.rstrip(',') != "action,data,expected result":
                continue
            try:
                cells = list(csv.reader(io.StringIO("\n".join(lines[i:i+6]))))
            except csv.Error:
                continue
            # Two supplied Photos CSVs have an extra empty header/row field
            # and an unquoted comma in the first Expected Result. Keep this
            # distinct testcase and record the explicit recovery for audit.
            malformed = header.endswith(',')
            rows = []
            for row in cells[1:]:
                if malformed and row and row[-1] == '':
                    row = row[:-1]
                if len(row) < 3 or (len(row) != 3 and not malformed):
                    break
                rows.append(dict(zip(['Action', 'Data', 'Expected Result'],
                                     [row[0], row[1], ','.join(row[2:])])))
            if len(rows) == 5 and all(r.get("Action") and r.get("Expected Result") for r in rows):
                return package(rows, item["line"], 'Dropped empty trailing CSV fields; joined extra Expected Result cells with commas.' if malformed else None)
    return None


def is_launch(command, names):
    if re.search(r"-ValidateOnly\b|-PreflightOnly\b", command, re.I):
        return False
    for match in re.finditer(r"(?:-File\s+|&\s+)(?:'([^']+\.ps1)'|\"([^\"]+\.ps1)\"|([^\s;]+\.ps1))", command, re.I):
        path = next(g for g in match.groups() if g)
        if Path(path.replace("\\", "/")).name.lower() in names:
            return True
    return False


def extract_run(path, root):
    records, errors = read_records(path)
    group = path.relative_to(root).parts[0]
    folder = path.parent.name
    app_key = next(key for key in APPS if folder.lower().startswith(key))
    start = stamp(records[0][1]["timestamp"])
    end = stamp(records[-1][1]["timestamp"])
    calls, by_id, outputs, users, messages, tokens, task_ends = [], {}, [], [], [], [], []
    models, providers = set(), set()
    for line, event in records:
        payload = event.get("payload", {})
        kind = payload.get("type")
        if event["type"] == "turn_context":
            models.add(payload.get("model", "unknown"))
        if event["type"] == "session_meta":
            providers.add(payload.get("model_provider", "unknown"))
        if event["type"] == "event_msg":
            if kind == "user_message":
                users.append({"line": line, "timestamp": event["timestamp"], "text": payload.get("message", "")})
            if kind == "task_complete":
                task_ends.append({"line": line, "timestamp": event["timestamp"], "duration_ms": payload.get("duration_ms")})
            if kind == "token_count" and payload.get("info", {}).get("total_token_usage"):
                tokens.append({"line": line, **payload["info"]["total_token_usage"]})
        if event["type"] != "response_item":
            continue
        if kind == "message" and payload.get("role") == "assistant":
            messages.append({"line": line, "timestamp": event["timestamp"], "text": "\n".join(c.get("text", "") for c in payload.get("content", []))})
        if kind in {"function_call", "custom_tool_call"}:
            args = payload.get("arguments", payload.get("input", ""))
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                pass
            command = args.get("command", args.get("cmd", args.get("code", ""))) if isinstance(args, dict) else str(args)
            item = {"line": line, "tool": payload["name"], "command": command, "timestamp": event["timestamp"], "call_id": payload.get("call_id")}
            item['action'] = args.get('action') if isinstance(args, dict) else None
            calls.append(item)
            by_id[payload.get("call_id")] = item
        if kind in {"function_call_output", "custom_tool_call_output"} and isinstance(payload.get("output"), str):
            call = by_id.get(payload.get("call_id"), {})
            outputs.append({"line": line, "timestamp": event["timestamp"], "command": call.get("command", ""),
                            "call_line": call.get("line"), "text": payload["output"], "tool": call.get("tool", ""), 'action': call.get('action')})

    final = messages[-1] if messages else None
    raw_end = end
    # A settings-only event can be appended hours after completed work. Use
    # the recorded task completion, retaining the full file span for audit.
    end_line = records[-1][0]
    if task_ends:
        end = stamp(task_ends[-1]["timestamp"])
        end_line = task_ends[-1]["line"]
    scripts = [{"file": str(p.relative_to(root)).replace("\\", "/"), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size, "lines": len(p.read_text(encoding="utf-8-sig").split("\n"))} for p in path.parent.glob("*.ps1")]
    names = {Path(s["file"]).name.lower() for s in scripts}
    if final:
        names.update(n.lower() for n in re.findall(r"([\w.-]+\.ps1)\b", final["text"]))
    # Some supplied filenames have an added copy suffix; recover original
    # generated names from the successful author's final message above.
    launches = [c for c in calls if c["tool"].endswith("shell_command") and is_launch(c["command"], names)]
    launch_lines = {c["line"] for c in launches}
    case = testcase_from_outputs(outputs)
    if not case:
        raise ValueError(f"No five-row testcase captured for {path}")
    actions = [row["Action"] for row in case["rows"]]
    first_pass, observations, executions, first_attempt_successes = {}, [], [], []
    for item in outputs:
        result_read = bool(re.search(r"Get-Content|Import-Csv", item["command"], re.I) and
                           re.search(r"(?:result|summary|report|run-log|evidence\.log|run\.log)[\w.*-]*\.(?:json|csv|txt|log)", item["command"], re.I) and
                           not re.search(r"Get-Content[^;\n]*\.ps1", item["command"], re.I))
        live_replay = item['tool'].endswith('agta_replay') or (item['tool'].endswith('agta_explore') and item.get('action') == 'Replay')
        eligible = item["call_line"] in launch_lines or result_read or live_replay
        if not eligible:
            continue
        text = body(item["text"])
        states = observed_steps(text, actions)
        elapsed = (stamp(item["timestamp"]) - start).total_seconds() / 60
        if live_replay:
            for index in first_attempt_steps(text, actions):
                first_attempt_successes.append({'stepIndex': index, 'minutes': elapsed, 'line': item['line']})
                first_pass.setdefault(str(index), {'minutes': elapsed, 'line': item['line'], 'source': 'first-attempt live step'})
        if states:
            observation = {"line": item["line"], "call_line": item["call_line"], "minutes": elapsed,
                           "states": states, "source": "execution" if item["call_line"] in launch_lines else "result read"}
            observations.append(observation)
            for index, status in states.items():
                if status == "PASS" and str(index) not in first_pass:
                    first_pass[str(index)] = {"minutes": elapsed, "line": item["line"]}
        parsed_executions = []
        for value in json_values(text):
            if isinstance(value, dict) and (value.get('qualifying') is False or value.get('runKind') == 'Diagnostic'):
                continue
            if isinstance(value, dict) and "steps" in value and "summary" in value and "executionId" in value:
                parsed_executions.append({"line": item["line"], "minutes": elapsed, "truncated": False,
                    **{key: value.get(key) for key in ("executionId", "ok", "summary", "cleanupOk", "interactionPolicy", "timing", "startedAt", "finishedAt")},
                    "assertions": [{"stepIndex": s.get("stepIndex"), "action": s.get("action"), "status": s.get("status"),
                                    "assertions": s.get("assertions", []), "error": s.get("error")} for s in value["steps"]]})
        if not parsed_executions:
            for header in execution_headers(text):
                parsed_executions.append({"line": item["line"], "minutes": elapsed,
                                          "truncated": True, **header, "assertions": []})
        executions.extend(parsed_executions)
    usage = tokens[-1] if tokens else {}
    resets = [b["line"] for a, b in zip(tokens, tokens[1:]) if b["total_tokens"] < a["total_tokens"]]
    counts = collections.Counter(c["tool"] for c in calls)
    complete = [o for o in observations if len(o["states"]) == 5 and set(o["states"].values()) == {"PASS"}]
    gaps = [(stamp(b[1]["timestamp"]) - stamp(a[1]["timestamp"])).total_seconds()/60 for a,b in zip(records,records[1:])]
    run = {"folder": folder, "group": group, "app": APPS[app_key], "app_key": app_key,
           "file": str(path.relative_to(root)).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
           "source_records": len(records), "parse_errors": errors, "start": start.isoformat(), "end": end.isoformat(),
           "minutes": (end-start).total_seconds()/60, "raw_log_span_minutes": (raw_end-start).total_seconds()/60,
           "end_line": end_line, "max_event_gap_minutes": max(gaps, default=0),
           "models": sorted(models), "providers": sorted(providers), "users": users, "final": final, "task_ends": task_ends,
           "usage": usage, "token_reset_lines": resets, "total_tokens": usage.get("total_tokens"),
           "output_tokens": usage.get("output_tokens"), "input_tokens": usage.get("input_tokens"),
           "cached_input_tokens": usage.get("cached_input_tokens"),
           "uncached_input_tokens": usage.get("input_tokens", 0) - usage.get("cached_input_tokens", 0) if usage else None,
           "tool_counts": dict(counts), "tool_calls": len(calls), "shell_calls": counts["shell_command"],
           "patch_calls": counts["apply_patch"], "image_calls": counts["view_image"],
           "tool_text_kib": sum(len(o["text"].encode()) for o in outputs)/1024,
           "launches": [{k: c[k] for k in ("line", "timestamp", "command")} for c in launches], "script_launches": len(launches),
           "scripts": scripts, "testcase": case, "first_pass": first_pass, "first_attempt_successes": first_attempt_successes, "observations": observations,
           "first_all_pass_minutes": complete[0]["minutes"] if complete else None,
           "last_all_pass_line": complete[-1]["line"] if complete else None, "executions": executions,
           "reported_pass_claim": bool(final and re.search(r"5\s*(?:/|of)\s*5|5\s+(?:\w+\s+){0,4}(?:pass|step|CSV)|all 5", final["text"], re.I)),
           "folder_failed_label": "failed" in folder.lower()}
    return run


def extract_all(root):
    # Allow-list both roots. Do not recurse through root/old, even if it has
    # matching filenames or a newer timestamp than an included run.
    paths = [p for group in GROUPS for p in (root/group).rglob("*.jsonl") if "old" not in {x.lower() for x in p.relative_to(root/group).parts}]
    runs = [extract_run(path, root) for path in paths]
    runs.sort(key=lambda r: (r["app"], r["group"], r["start"], r["folder"]))
    counters = collections.Counter()
    for run in runs:
        key = run["group"], run["app_key"]
        counters[key] += 1
        run["id"] = f"{'N' if run['group']=='native' else 'F'}-{run['app_key'].upper()}-{counters[key]:02d}"
    hashes = [r["sha256"] for r in runs]
    if len(hashes) != len(set(hashes)):
        raise ValueError("Duplicate input logs; resolve before reporting independent sessions")
    return {"schema_version": 1, "source_root": str(root), "included_roots": list(GROUPS),
            "exclusion": "old directory excluded by allow-list", "runs": runs}


METRICS = ["minutes", "total_tokens", "output_tokens", "uncached_input_tokens", "cached_input_tokens", "script_launches", "patch_calls", "shell_calls", "image_calls", "tool_calls", "tool_text_kib"]


def stats(values):
    values = [v for v in values if v is not None]
    return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "min": min(values), "max": max(values), "sd": statistics.stdev(values) if len(values)>1 else None} if values else None


def summarize(runs):
    return {group: {metric: stats([r[metric] for r in runs if r["group"] == group]) for metric in METRICS} for group in GROUPS}
