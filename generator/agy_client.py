#!/usr/bin/env python3
"""Antigravity CLI backend: calls `agy` non-interactively for inference.

Bypasses local Ollama inference and connects the Stratum IF pipeline to
frontier models (Gemini 3.1 Pro, etc.) via the local `agy` toolchain.
"""

import json
import os
import re
import shutil
import subprocess
import time
from llm_client import LlmClient, LlmCallError


class AgyClient(LlmClient):
    """LlmClient implementation dispatching prompts to the `agy` CLI."""

    def __init__(self, model=None, effort=None, agy_path=None, echo=True):
        super().__init__()
        self.model = model or os.environ.get("AGY_MODEL", os.environ.get("STRATUM_MODEL", "gemini-3.1-pro-high"))
        self.effort = effort or os.environ.get("AGY_EFFORT")
        self.agy_path = agy_path or os.environ.get("AGY_PATH") or shutil.which("agy") or "/home/krazy/.local/bin/agy"
        self.echo = echo
        self.last_call = {}

    def _resolve_model_and_effort(self, think):
        """Map model and thinking flags to agy flags.

        For models with -high / -low naming (like gemini-3.1-pro-high):
        - think=False maps to -low
        - think=True (or None) maps to -high
        For models or sessions using --effort:
        - think=False maps to --effort low
        - think=True maps to --effort high
        """
        model = self.model
        effort = self.effort

        if model:
            if think is False:
                if model.endswith("-high"):
                    return model[:-5] + "-low", None
                elif model.endswith("-medium"):
                    return model[:-7] + "-low", None
                elif model.endswith("-low"):
                    return model, None
                else:
                    return model, effort or "low"
            else:
                if model.endswith("-low"):
                    return model[:-4] + "-high", None
                elif model.endswith("-medium"):
                    return model[:-7] + "-high", None
                elif model.endswith("-high"):
                    return model, None
                else:
                    return model, effort or "high"
        else:
            return None, "low" if think is False else (effort or "high")

    def run_prompt(self, prompt, **kwargs):
        """Run a single prompt through agy and return (thinking, response)."""
        think = kwargs.get("think")
        schema = kwargs.get("format")
        limits = kwargs.get("limits") or {}

        model_to_use, effort_to_use = self._resolve_model_and_effort(think)

        cmd = [self.agy_path, "--output-format", "json", "--disable-slash-commands"]
        if model_to_use:
            cmd.extend(["--model", model_to_use])
        if effort_to_use:
            cmd.extend(["--effort", effort_to_use])

        format_sent = False
        if schema is not None and isinstance(schema, dict):
            cmd.extend(["--json-schema", json.dumps(schema)])
            format_sent = True

        timeout = limits.get("max_seconds")
        if timeout is not None:
            timeout = max(int(timeout), 60)
        else:
            timeout = 1800

        max_attempts = 3
        last_error = None
        for attempt in range(1, max_attempts + 1):
            started = time.time()
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                elapsed = round(time.time() - started, 2)
                self.last_call = {
                    'seconds': elapsed,
                    'aborted': 'wall_clock',
                    'done_reason': 'timeout',
                    'format_sent': format_sent,
                }
                raise LlmCallError(f"agy call timed out after {elapsed:.1f}s")

            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or proc.stdout.strip()
                last_error = LlmCallError(f"agy failed with code {proc.returncode}: {err_msg}")
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                self.last_call = {
                    'seconds': round(time.time() - started, 2),
                    'aborted': 'error',
                    'done_reason': 'error',
                    'format_sent': format_sent,
                    'crash_retries': attempt - 1,
                }
                raise last_error

            # Parse JSON output from agy
            raw_output = proc.stdout.strip()
            try:
                data = json.loads(raw_output)
            except json.JSONDecodeError:
                start, end = raw_output.find('{'), raw_output.rfind('}')
                if start != -1 and end > start:
                    try:
                        data = json.loads(raw_output[start:end + 1])
                    except json.JSONDecodeError:
                        last_error = LlmCallError(f"Could not parse agy output as JSON: {raw_output[:500]}")
                        if attempt < max_attempts:
                            time.sleep(2)
                            continue
                        raise last_error
                else:
                    last_error = LlmCallError(f"Could not parse agy output as JSON: {raw_output[:500]}")
                    if attempt < max_attempts:
                        time.sleep(2)
                        continue
                    raise last_error

            if data.get("status") == "ERROR":
                last_error = LlmCallError(f"agy reported error: {data.get('error')}")
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                raise last_error

            if "structured_output" in data and data["structured_output"] is not None:
                response_text = json.dumps(data["structured_output"])
            else:
                response_text = data.get("response", "")
                # Strip markdown code blocks if the model wrapped its output
                clean = response_text.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
                    clean = re.sub(r"\n?```$", "", clean)
                    response_text = clean.strip()

            if not response_text.strip():
                last_error = LlmCallError("agy returned an empty response")
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                raise last_error

            usage = data.get("usage") or {}
            duration = data.get("duration_seconds", time.time() - started)
            prompt_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            thinking_tokens = usage.get("thinking_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            thinking_text = f"[Agy thinking tokens: {thinking_tokens}]" if thinking_tokens > 0 else ""

            self.last_call = {
                'seconds': round(duration, 2),
                'thinking_bytes': len(thinking_text.encode('utf-8')),
                'response_bytes': len(response_text.encode('utf-8')),
                'prompt_tokens': prompt_tokens,
                'output_tokens': output_tokens,
                'thinking_tokens': thinking_tokens,
                'total_tokens': total_tokens,
                'done_reason': 'stop',
                'format_sent': format_sent,
                'aborted': None,
                'crash_retries': attempt - 1,
            }

            if self.echo:
                model_disp = model_to_use or "default"
                retries_disp = f" (retry {attempt-1})" if attempt > 1 else ""
                print(f"  [{model_disp}] {duration:.1f}s | in: {prompt_tokens} | out: {output_tokens} (think: {thinking_tokens}){retries_disp}")

            return thinking_text, response_text
