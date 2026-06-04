"""Vision-LLM judge + best-of-N retry loop for the protein-inspect view battery.

Reads rendered PNGs back, asks a Claude vision model to score them against a
per-view rubric declared in view_battery.yaml, and re-renders failing views
with pre-declared `retry_knobs` (parameter overrides) until either the rubric
passes or the retry budget is exhausted. The highest-scoring attempt's PNG is
the one left on disk under the original `output_path` — downstream code
(montage, summary) is untouched.

Public entry point: `judge_and_retry`. Everything else is module-private.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from protein_inspect.pymol_runner import PyMOLRunner, RenderPlanItem

log = logging.getLogger("protein_inspect.view_judge")

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_PASS_THRESHOLD = 4
DEFAULT_MAX_RETRIES = 2

_SYSTEM_PROMPT = [{
    "type": "text",
    "text": (
        "You are a strict visual QA judge for scientific protein figures.\n"
        "Score each image against the provided rubric on a 0-5 integer scale:\n"
        "  5 = rubric fully satisfied, publication quality\n"
        "  4 = minor cosmetic issues, all required information legible\n"
        "  3 = usable but one important rubric element is degraded\n"
        "  2 = a key rubric element is missing or unreadable\n"
        "  1 = image is mostly uninterpretable\n"
        "  0 = image is blank, all-black, or shows wrong content\n"
        "Output ONLY valid JSON. Do not include prose, markdown fences, or commentary.\n"
        "Schema: {\"score\": <int 0-5>, \"pass\": <bool>, "
        "\"issues\": [<short string>, ...], "
        "\"worst_issue\": \"<one-line summary or empty string>\"}"
    ),
    "cache_control": {"type": "ephemeral"},
}]


def judge_and_retry(
    results: list[dict],
    plan: list[RenderPlanItem],
    runner: PyMOLRunner,
    *,
    model: str = DEFAULT_MODEL,
    pass_threshold: int | None = None,
    max_retries: int | None = None,
) -> list[dict]:
    """Score every successfully-rendered view; re-render failing ones up to N times.

    Mutates files on disk so each `output_path` ends up holding the highest-
    scoring attempt's PNG. Never raises into the pipeline: judge / API / render
    failures are logged and surfaced via a per-item `judge: {error: ...}` dict.
    """
    cfg = _load_judge_config(runner)
    pass_threshold = pass_threshold if pass_threshold is not None else cfg["pass_threshold"]
    max_retries = max_retries if max_retries is not None else cfg["max_retries"]

    client = _make_client()
    if client is None:
        for r in results:
            r["judge"] = {"error": "no api key"}
        return results

    by_name = {item.view_name: item for item in plan}
    n_calls = 0
    n_retries = 0

    for r in results:
        if not r.get("ok"):
            continue
        view_name = r["name"]
        plan_item = by_name.get(view_name)
        if plan_item is None:
            continue
        view_def = runner.views.get(view_name, {})
        rubric = view_def.get("judge_rubric")
        if not rubric:
            log.info("no judge_rubric for %s, skipping judge", view_name)
            continue

        output_path = Path(r["path"])
        params = r.get("details", {}) or plan_item.params
        retry_knobs = view_def.get("retry_knobs") or []

        best_score = -1
        best_attempt = 0
        best_issues: list[str] = []
        knobs_used: list[str] = []
        shadow = output_path.with_suffix(output_path.suffix + ".best")
        attempts_made = 0
        final_score = 0

        try:
            for attempt in range(max_retries + 1):
                attempts_made = attempt + 1
                total = max_retries + 1
                try:
                    verdict = _judge_png(
                        client, model, output_path, view_name, view_def,
                        params, attempt, total,
                    )
                    n_calls += 1
                except Exception as e:
                    log.warning("judge api error for %s: %s", view_name, e)
                    r["judge"] = {"error": f"api: {e}"}
                    break

                score = verdict["score"]
                passed = verdict["pass"] and score >= pass_threshold
                issues = verdict["issues"]
                log.info(
                    "judged %s attempt %d/%d: score=%d (%s)",
                    view_name, attempt + 1, total, score,
                    "pass" if passed else "fail",
                )

                if score > best_score:
                    best_score = score
                    best_attempt = attempt
                    best_issues = issues
                    if attempt < max_retries:
                        try:
                            shutil.copyfile(output_path, shadow)
                        except OSError as e:
                            log.warning("shadow copy failed for %s: %s", view_name, e)

                final_score = score
                if passed:
                    break

                if attempt >= max_retries:
                    break
                if attempt >= len(retry_knobs):
                    log.info("no more retry_knobs for %s, keeping best", view_name)
                    break

                knob = retry_knobs[attempt]
                knob_name = knob.get("name", f"knob_{attempt}")
                overrides = knob.get("overrides", {}) or {}
                log.info("retrying %s with knob %s", view_name, knob_name)
                try:
                    _rerender_with_overrides(
                        runner, view_name, params, output_path, overrides,
                    )
                    knobs_used.append(knob_name)
                    n_retries += 1
                except Exception as e:
                    log.warning("re-render failed for %s: %s", view_name, e)
                    break

            if best_score >= 0 and best_attempt != attempts_made - 1 and shadow.exists():
                try:
                    shutil.copyfile(shadow, output_path)
                    final_score = best_score
                except OSError as e:
                    log.warning("restore best-of-N failed for %s: %s", view_name, e)

            if "judge" not in r:
                r["judge"] = {
                    "final_score": int(final_score),
                    "attempts": attempts_made,
                    "knobs_used": knobs_used,
                    "issues": best_issues if best_score == final_score else [],
                }
        finally:
            if shadow.exists():
                try:
                    shadow.unlink()
                except OSError:
                    pass

    log.info("judge summary: %d calls, %d retries", n_calls, n_retries)
    return results


def _load_judge_config(runner: PyMOLRunner) -> dict:
    judge_defaults = (runner.defaults or {}).get("judge", {}) or {}
    return {
        "pass_threshold": int(judge_defaults.get("pass_threshold", DEFAULT_PASS_THRESHOLD)),
        "max_retries": int(judge_defaults.get("max_retries", DEFAULT_MAX_RETRIES)),
        "model": judge_defaults.get("model", DEFAULT_MODEL),
    }


def _make_client():
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.warning("ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN not set — view judge disabled")
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed — view judge disabled")
        return None
    try:
        return anthropic.Anthropic()
    except Exception as e:
        log.warning("anthropic client init failed: %s", e)
        return None


def _judge_png(client, model: str, png_path: Path, view_name: str,
               view_def: dict, params: dict, attempt: int, total: int) -> dict:
    img_b64 = base64.standard_b64encode(png_path.read_bytes()).decode("ascii")
    rubric = view_def.get("judge_rubric", "").strip()
    description = view_def.get("description", "").strip()

    try:
        import yaml as _yaml
        params_yaml = _yaml.safe_dump(dict(params), default_flow_style=False).strip()
    except Exception:
        params_yaml = json.dumps(dict(params))

    stable_text = (
        f"View: {view_name}\n"
        f"Intent: {description}\n\n"
        f"Rubric for a GOOD render:\n{rubric}\n\n"
        f"Parameters used:\n{params_yaml}"
    )
    volatile_text = f"Attempt: {attempt + 1} of {total}\nReturn the JSON object."

    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": stable_text,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": volatile_text},
            ],
        }],
    )
    text = response.content[0].text if response.content else ""
    return _parse_verdict(text)


def _parse_verdict(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        score = max(0, min(5, int(data.get("score", 3))))
        passed = bool(data.get("pass", False))
        issues = data.get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]
        issues = [str(x)[:120] for x in issues[:3]]
        return {"score": score, "pass": passed, "issues": issues}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning("judge returned malformed JSON: %s", e)
        return {"score": 3, "pass": False, "issues": ["malformed judge response"]}


def _apply_overrides(commands: list[dict], overrides: dict) -> list[dict]:
    """Deep-copy commands and patch matching `set <name> ...` / `zoom` args."""
    patched = copy.deepcopy(commands)
    matched: dict[str, int] = {k: 0 for k in overrides}
    for cmd in patched:
        fn = cmd.get("fn")
        args = cmd.get("args") or []
        if fn == "set" and len(args) >= 2:
            key = args[0]
            if key in overrides:
                args[1] = overrides[key]
                matched[key] = matched.get(key, 0) + 1
        elif fn == "zoom" and "zoom" in overrides and len(args) >= 2:
            args[1] = overrides["zoom"]
            matched["zoom"] = matched.get("zoom", 0) + 1
    for key, count in matched.items():
        if count == 0:
            log.warning("retry knob override %r matched no commands", key)
    return patched


def _rerender_with_overrides(runner: PyMOLRunner, view_name: str, params: dict,
                              output_path: Path, overrides: dict) -> None:
    original = runner.views[view_name]
    patched_def = copy.deepcopy(original)
    patched_def["commands"] = _apply_overrides(original.get("commands", []), overrides)
    runner.views[view_name] = patched_def
    try:
        runner.render_view(view_name, params, output_path)
    finally:
        runner.views[view_name] = original
