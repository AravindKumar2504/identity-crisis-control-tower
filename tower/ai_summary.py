"""An optional plain-English summary of one result, written by a language model.

The rules make every verdict; the model only puts the tool's own results into plain words. It reads what the
screen shows (the verdict, the reasons, the next steps, what the tool can't tell, and the release changes), never
the raw data files, and every finding and sample id it cites is checked against those results.

It runs on a local model through Ollama by default (no key, no internet), or on Claude when the user sets their
own ANTHROPIC_API_KEY. No key is stored in this repo.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
LOCAL_MODEL = os.environ.get("TOWER_LOCAL_MODEL", "qwen3:8b")
CLAUDE_MODEL = os.environ.get("TOWER_CLAUDE_MODEL", "claude-sonnet-5-5")
SAMPLE = re.compile(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}(?:-\d{2}[A-Z]?)?")
FINDING = re.compile(r"\bF\d+\b")
PLAIN = {"sample_swap": "swapped samples", "duplicate": "copied profiles", "membership_change": "samples missing or new",
         "label_conflict": "changed labels", "missing_data": "values removed", "other": "unexplained change",
         "join_inflation": "rows multiplied by a table join", "unlinked_record": "record with no matching sample"}

SYSTEM = """You write a short plain-English summary of a data-quality tool's results for a research data engineer.
Rules:
- Use only facts in the JSON you are given. Never add numbers, sample ids, causes or advice that are not in it.
- Start with the verdict for the research question, using the exact verdict word.
- Then say which release changes touch this question and why they matter. If none touch it, say so and explain the verdict from the reasons.
- Cite only the finding ids listed under release_changes_that_touch_this_question, in square brackets, like [F1]. Never put anything else in square brackets.
- Then give the first next step and one thing the tool can't tell.
- Write 4 to 6 sentences in one paragraph: no lists, no headings, no em dashes.
- No diagnosis, treatment advice or clinical claims."""


class ModelUnavailable(RuntimeError):
    """No language model could be reached; the message says how to start one."""


def backend() -> str:
    """Which model the summary would use, in words for the screen."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return f"Claude ({CLAUDE_MODEL}), with your own API key"
    return f"a local model on this computer ({LOCAL_MODEL} through Ollama), with no key and no internet"


def context(ready: dict, findings: dict | None, release: str | None = None) -> dict:
    """The tool's own results for one question, as the screen shows them. No raw data, and only the release
    changes that touch this question."""
    ctx = {"research_question": ready["card"]["title"], "release": release or ready["release"]["name"],
           "verdict": ready["verdict"], "reasons": list(ready["reasons"])[:6],
           "next_steps": [s["step"] for s in ready.get("next_steps") or []][:4],
           "what_the_tool_cant_tell": list(ready.get("cannot_tell") or [])[:3]}
    if findings:
        touching = {t["finding"] for t in ready.get("release_changes") or []}
        rel = [f for f in findings["findings"] if f["id"] in touching]
        ctx["release_changes_that_touch_this_question"] = [
            {"id": f["id"], "kind": PLAIN.get(f["kind"], f["kind"]), "severity": f["severity"],
             "samples": [e["id"] for e in f["evidence"] if e.get("kind") == "sample"][:12],
             "affects": f.get("affects_analyses") or [], "summary": f["summary"]}
            for f in rel[:12]]
        ctx["release_changes_that_do_not_touch_this_question"] = len(findings["findings"]) - len(rel)
    return ctx


def ask(system: str, user: str) -> tuple[str, str]:
    """Send one prompt. Returns (the text, which model wrote it)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        body = {"model": CLAUDE_MODEL, "max_tokens": 500, "system": system,
                "messages": [{"role": "user", "content": user}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
                                     {"x-api-key": key, "anthropic-version": "2023-06-01",
                                      "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise ModelUnavailable(f"Claude returned HTTP {e.code}. Check your API key, or unset ANTHROPIC_API_KEY "
                                   "to use the local model.") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise ModelUnavailable(f"Claude couldn't be reached ({e}). Unset ANTHROPIC_API_KEY to use the local "
                                   "model.") from None
        return "".join(b.get("text", "") for b in data.get("content", [])), f"Claude ({CLAUDE_MODEL})"
    body = {"model": LOCAL_MODEL, "stream": False, "think": False, "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_predict": 400},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", json.dumps(body).encode(), {"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ModelUnavailable(f"The local model {LOCAL_MODEL} isn't downloaded: run `ollama pull {LOCAL_MODEL}` "
                                   "once (about 5 GB).") from None
        raise ModelUnavailable(f"The local model returned HTTP {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise ModelUnavailable("No language model is running. Start the local one with `ollama serve` (and "
                               f"`ollama pull {LOCAL_MODEL}` once), or set your own ANTHROPIC_API_KEY before "
                               "starting the screen.") from None
    return (data.get("message") or {}).get("content", ""), f"{LOCAL_MODEL} on this computer"


def check(text: str, ready: dict, findings: dict | None) -> dict:
    """Every finding and sample id the text cites must be one the model was given: a release change that touches
    this question, or a sample named in this question's results."""
    ctx = context(ready, findings)
    known_f = {f["id"] for f in ctx.get("release_changes_that_touch_this_question", [])}
    known_s = set(SAMPLE.findall(json.dumps(ctx, default=str)))
    cited_f = sorted(set(FINDING.findall(text)), key=lambda x: int(x[1:]))
    cited_s = sorted(set(SAMPLE.findall(text)))
    unknown = [x for x in cited_f if x not in known_f] + [
        s for s in cited_s if s not in known_s and not any(k.startswith(s + "-") for k in known_s)]
    states = bool(re.search(rf"\b{re.escape(ready['verdict'])}\b", text, re.I))
    return {"cited": len(cited_f) + len(cited_s), "unknown": unknown, "states_verdict": states}


def summarize(ready: dict, findings: dict | None, release: str | None = None) -> dict:
    """Write the summary and check it. Raises ModelUnavailable when no model can be reached."""
    user = "Results:\n```json\n" + json.dumps(context(ready, findings, release), indent=1) + "\n```\nWrite the summary."
    t0 = time.time()
    text, model = ask(SYSTEM, user)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if not text:
        raise ModelUnavailable("The model returned an empty answer. Try again.")
    c = check(text, ready, findings)
    return {"text": text, "model": model, "seconds": time.time() - t0,
            "citations": {"cited": c["cited"], "unknown": c["unknown"]}, "states_verdict": c["states_verdict"]}
