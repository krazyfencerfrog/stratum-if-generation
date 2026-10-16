#!/usr/bin/env python3
"""Claude Code CLI backend: calls `claude -p` non-interactively for inference.

Runs the Stratum IF pipeline on a Claude subscription (or whatever auth the
local Claude Code install uses) instead of local Ollama inference. Each call
is a single stateless completion: tools, MCP servers, skills, CLAUDE.md
discovery and session persistence are all switched off, and the Claude Code
system prompt is replaced with a minimal one.

Environment:
  STRATUM_CLAUDE_MODEL       model or alias (opus, sonnet, haiku, claude-...);
                             falls back to STRATUM_MODEL, then the CLI default
  STRATUM_CLAUDE_EFFORT      effort for thinking calls (default high);
                             think=False calls always run at low
  STRATUM_CLAUDE_PATH        path to the claude executable
  STRATUM_CLAUDE_LIMIT_WAIT  seconds to sleep when the usage limit is hit
                             (default 900)
  STRATUM_CLAUDE_LIMIT_MAX   total seconds to keep waiting on usage limits
                             before giving up (default 21600)

(Claude Code sets CLAUDE_EFFORT etc. in its own environment, hence the
STRATUM_ prefix.)
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from llm_client import LlmClient, LlmCallError


SYSTEM_PROMPT = ("You are a text generation backend for an automated story pipeline. "
                 "Follow the user's instructions exactly and reply with only the requested output.")

LIMIT_PATTERN = re.compile(r"usage limit|hit your limit|rate limit|rate_limit|overloaded|\b429\b|\b529\b", re.I)


class ClaudeClient(LlmClient):
    """LlmClient implementation dispatching prompts to the `claude` CLI."""

    def __init__(self, model=None, effort=None, claude_path=None, echo=True):
        super().__init__()
        self.model = model or os.environ.get("STRATUM_CLAUDE_MODEL") or os.environ.get("STRATUM_MODEL") or None
        self.effort = effort or os.environ.get("STRATUM_CLAUDE_EFFORT") or "high"
        self.claude_path = (claude_path or os.environ.get("STRATUM_CLAUDE_PATH") or shutil.which("claude")
                            or os.path.expanduser("~/.local/bin/claude"))
        self.limit_wait = int(os.environ.get("STRATUM_CLAUDE_LIMIT_WAIT", 900))
        self.limit_max = int(os.environ.get("STRATUM_CLAUDE_LIMIT_MAX", 21600))
        self.echo = echo
        self.last_call = {}
        # an empty working directory keeps the repo's CLAUDE.md / GEMINI.md
        # out of the model's context
        self.workdir = tempfile.mkdtemp(prefix="stratum_claude_")

    def _effort_for(self, think):
        return "low" if think is False else self.effort

    def _build_cmd(self, think, schema):
        cmd = [self.claude_path, "-p", "--output-format", "json",
               "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
               "--no-session-persistence", "--system-prompt", SYSTEM_PROMPT,
               "--effort", self._effort_for(think)]
        if self.model:
            cmd.extend(["--model", self.model])
        if isinstance(schema, dict):
            cmd.extend(["--json-schema", json.dumps(schema)])
        return cmd

    @staticmethod
    def _is_limit(text, data=None):
        status = (data or {}).get("api_error_status")
        return status in (429, 529) or bool(LIMIT_PATTERN.search(text or ""))

    def run_prompt(self, prompt, **kwargs):
        """Run a single prompt through claude and return (thinking, response)."""
        think = kwargs.get("think")
        schema = kwargs.get("format")
        limits = kwargs.get("limits") or {}

        cmd = self._build_cmd(think, schema)
        format_sent = isinstance(schema, dict)

        timeout = limits.get("max_seconds")
        timeout = max(int(timeout), 60) if timeout is not None else 1800

        max_attempts = 3
        attempt = 0
        limit_waited = 0
        while True:
            attempt += 1
            started = time.time()
            try:
                # its own session: claude never sees the terminal, so ctrl-c
                # interrupts this process (and subprocess.run kills claude)
                # instead of killing claude and leaving the retry loop to go on
                proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                      timeout=timeout, cwd=self.workdir, start_new_session=True)
            except subprocess.TimeoutExpired:
                elapsed = round(time.time() - started, 2)
                self.last_call = {
                    'seconds': elapsed,
                    'aborted': 'wall_clock',
                    'done_reason': 'timeout',
                    'format_sent': format_sent,
                }
                raise LlmCallError(f"claude call timed out after {elapsed:.1f}s")

            raw_output = proc.stdout.strip()
            data = None
            try:
                data = json.loads(raw_output)
            except json.JSONDecodeError:
                start, end = raw_output.find('{'), raw_output.rfind('}')
                if start != -1 and end > start:
                    try:
                        data = json.loads(raw_output[start:end + 1])
                    except json.JSONDecodeError:
                        pass

            if data is None or proc.returncode != 0 or data.get("is_error"):
                err_msg = (data or {}).get("result") or proc.stderr.strip() or raw_output
                err_msg = str(err_msg)[:500]
                if self._is_limit(err_msg, data):
                    if limit_waited >= self.limit_max:
                        raise LlmCallError(f"claude usage limit persisted for {limit_waited}s: {err_msg}",
                                           http_status=429)
                    if self.echo:
                        print(f"  [claude] Usage limit reached ({err_msg.strip()}). Pausing for {self.limit_wait}s...")
                    time.sleep(self.limit_wait)
                    limit_waited += self.limit_wait
                    attempt -= 1    # waiting out a limit does not spend an attempt
                    continue
                if data is None:
                    last_error = LlmCallError(f"Could not parse claude output as JSON: {raw_output[:500]}")
                else:
                    last_error = LlmCallError(f"claude failed ({data.get('subtype') or proc.returncode}): {err_msg}")
                if attempt < max_attempts:
                    time.sleep(attempt * 4)
                    continue
                self.last_call = {
                    'seconds': round(time.time() - started, 2),
                    'aborted': 'error',
                    'done_reason': 'error',
                    'format_sent': format_sent,
                    'crash_retries': attempt - 1,
                }
                raise last_error

            if data.get("structured_output") is not None:
                response_text = json.dumps(data["structured_output"])
            else:
                response_text = data.get("result") or ""
                # Strip markdown code blocks if the model wrapped its output
                clean = response_text.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
                    clean = re.sub(r"\n?```$", "", clean)
                    response_text = clean.strip()

            if not response_text.strip():
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                raise LlmCallError("claude returned an empty response")

            usage = data.get("usage") or {}
            duration = (data.get("duration_ms") or (time.time() - started) * 1000) / 1000
            prompt_tokens = ((usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0)
                             + (usage.get("cache_read_input_tokens") or 0))
            output_tokens = usage.get("output_tokens") or 0
            thinking_tokens = (usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0

            thinking_text = f"[Claude thinking tokens: {thinking_tokens}]" if thinking_tokens > 0 else ""

            self.last_call = {
                'seconds': round(duration, 2),
                'thinking_bytes': len(thinking_text.encode('utf-8')),
                'response_bytes': len(response_text.encode('utf-8')),
                'prompt_tokens': prompt_tokens,
                'output_tokens': output_tokens,
                'thinking_tokens': thinking_tokens,
                'total_tokens': prompt_tokens + output_tokens,
                'done_reason': 'length' if data.get("stop_reason") == "max_tokens" else 'stop',
                'format_sent': format_sent,
                'aborted': None,
                'crash_retries': attempt - 1,
            }

            if self.echo:
                model_disp = next(iter(data.get("modelUsage") or {}), None) or self.model or "default"
                retries_disp = f" (retry {attempt-1})" if attempt > 1 else ""
                print(f"  [{model_disp}] {duration:.1f}s | in: {prompt_tokens} | out: {output_tokens} "
                      f"(think: {thinking_tokens}){retries_disp}")

            return thinking_text, response_text
