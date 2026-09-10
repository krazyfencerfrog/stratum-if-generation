#!/usr/bin/env python3
from llm_client import LlmClient
import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def _ollama_url(host, path):
    return host.rstrip("/") + path

class OllamaClient(LlmClient):
    def __init__(self, host=DEFAULT_OLLAMA_HOST, model='my model', keep_alive='30m', idle_timeout=180, max_duration=1800, echo=True):
        self.host = host
        self.model = model
        self.keep_alive = keep_alive
        self.idle_timeout = idle_timeout
        self.max_duration = max_duration
        self.echo = echo

    def run_prompt(self, prompt):
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": self.keep_alive,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _ollama_url(self.host, "/api/generate"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.time()
        thinking_chunks = []
        chunks = []
        try:
            with urllib.request.urlopen(req, timeout=self.idle_timeout) as response:
                for raw_line in response:
                    if time.time() - start > self.max_duration:
                        raise RuntimeError(
                            f"ollama call exceeded the overall {self.max_duration}s limit "
                            f"(see --timeout). This is a total-duration safety cap, separate "
                            f"from --idle-timeout ({self.idle_timeout}s), which fires only if the "
                            f"model stops producing output entirely rather than just taking "
                            f"a long time."
                        )
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # ignore stray non-JSON lines rather than aborting the call
                    if "error" in obj:
                        raise RuntimeError(f"ollama returned an error: {obj['error']}")
                    fragment = obj.get("response", "")
                    if fragment:
                        chunks.append(fragment)
                        if self.echo:
                            print(fragment, end="", flush=True)
                        if fragment.find('</think>') != -1:
                            thinking_chunks = chunks
                            chunks = []
                    if obj.get("done"):
                        if self.echo:
                            print()  # newline after the streamed response
                        break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ollama HTTP {e.code} error: {body}")
        except urllib.error.URLError as e:
            # A timeout that occurs during connection/header setup sometimes
            # surfaces wrapped inside URLError rather than as a raw
            # socket.timeout (which python raises instead if the timeout
            # happens later, while iterating the streamed body -- the more
            # likely case here). Check for both so the diagnostic message is
            # never misleadingly "can't reach ollama" when the real problem is
            # exactly the idle-timeout / mid-generation-unload scenario this
            # script exists to catch.
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise RuntimeError(_idle_timeout_message(self.keep_alive, self.idle_timeout))
            raise RuntimeError(
                f"could not reach ollama at {host} ({e.reason}). Is `ollama serve` running "
                f"there? Set --ollama-host or the OLLAMA_HOST environment variable if it's "
                f"not on the default address."
            )
        except socket.timeout:
            raise RuntimeError(_idle_timeout_message(self.keep_alive, self.idle_timeout))
        return ("".join(thinking_chunks).strip(), "".join(chunks).strip())


def _idle_timeout_message(keep_alive, idle_timeout):
    return (
        f"ollama produced no output for more than --idle-timeout ({idle_timeout}s). "
        f"This is the exact symptom of the model unloading mid-generation -- check "
        f"`ollama ps` right after this fails; if the model is gone, try a longer "
        f"--keep-alive (currently {keep_alive!r}; '-1' means never expire from "
        f"idleness), or raise --idle-timeout if this is just a slow cold model load."
    )

'''
def unload_model(model, host):
    """Best-effort: ask ollama to unload the model immediately (keep_alive=0),
    so it doesn't sit resident in memory until the idle timer eventually
    expires on its own. Called from a `finally` block, so this runs whether
    the overall generation run succeeded or failed. Never raises -- this is
    cleanup, not critical path, and a failure here shouldn't mask or replace
    whatever real error the run may have already hit."""
    try:
        payload = {"model": model, "prompt": "", "keep_alive": 0}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _ollama_url(host, "/api/generate"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print(f"(asked ollama to unload {model})")
    except Exception as e:
        print(f"NOTE: could not confirm ollama unloaded '{model}' ({e}) -- not fatal.", file=sys.stderr)
'''

        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model tag to run")
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST,
                         help="Base URL of the Ollama server (default: $OLLAMA_HOST or http://localhost:11434)")
    parser.add_argument("--keep-alive", default="30m",
                         help="Sent on every request so the server has no ambiguity about the model "
                              "being in use. Ollama duration string ('30m'), seconds as a number, "
                              "or '-1' for never-expire-from-idleness. Default: 30m")
    parser.add_argument("--retries", type=int, default=1, help="Retries per group on validation failure")
    parser.add_argument("--timeout", type=int, default=1800,
                         help="Overall wall-clock cap in seconds for a single generate call "
                              "(default: 1800 = 30 min). Separate from --idle-timeout.")
    parser.add_argument("--idle-timeout", type=int, default=180,
                         help="Seconds of complete silence (no new output at all) before giving up "
                              "on a call -- this is what actually catches the model getting "
                              "unloaded mid-generation. Also covers cold model load time, since "
                              "that's the wait before the first byte arrives; raise this if you're "
                              "using a large or slow-loading model. Default: 180")
    args = parser.parse_args()
    client = OllamaClient(host=args.ollama_host,
                          model=args.model,
                          keep_alive=args.keep_alive,
                          idle_timeout=args.idle_timeout,
                          max_duration=args.timeout,
                          echo=True);
    print('enter prompt and close stdin:')
    print(client.run_prompt(sys.stdin.read()))
