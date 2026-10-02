# TODO

Ordered. Items marked "after" wait for the runs they name, so their results
are not mixed with the change.

## In progress

- [ ] Branch comparison on kernel1, main line only, reusing the archived
      phase 3: `scripts/compare_kernel1.sh`, outputs in `../stratum-compare/`.
      `request-4-outline-loop-opus` done (about 1.0 h);
      `request-4-combined` running.
- [ ] Q5 against i1-IQ3_M: run the same premise call (3.5) on
      `qwen3.8_27b_unc_q5-128k` and on
      `hf.co/mradermacher/Qwen3.8-27B-OBLITERATED-i1-GGUF:i1-IQ3_M`; compare
      time, thinking size, whether the answer was forced, and the premise's
      quality. Check that `ollama ps` shows the IQ3_M at 100% GPU. Note that
      this changes the abliteration as well as the quant.

## After both comparisons

- [ ] Move the premise audit (3.5v) back to thinking on. On the opus run the
      thinking-off audit passed a turn whose task was the decision axis as a
      two-way pick ("force the final call: open the vent ... or hold the
      line"), the failure the audit exists to catch. Change the call's class
      in `generator/stats.py` (combined) / `generator/call_policy.py` (opus)
      from the thinking-off class to the judge class; keep its rationale
      field and schema. Re-run kernels 28 and 29 to 3.5 to confirm it catches
      the planted problems.
- [ ] Update the Ollama service settings (`sudo systemctl edit ollama`, then
      `sudo systemctl restart ollama`; only between runs, a restart kills a
      running job):
      ```
      [Service]
      Environment="OLLAMA_FLASH_ATTENTION=1"
      Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
      Environment="OLLAMA_MAX_LOADED_MODELS=1"
      Environment="OLLAMA_NUM_PARALLEL=1"
      ```
      Then confirm on the next load's log
      (`journalctl -u ollama -b | grep -iE "kv_cache|offload"`) that the
      cache shows `K (q8_0)` at about 1024 MiB instead of 2048, and how many
      layers moved to the GPU.

## Noted, not scheduled

- Model tags with typo'd context sizes: `num_ctx 129072` (meant 131072) and
  `64536` (meant 65536). Harmless for the pipeline, which sends 32768.
- `huihui-64k` has no chat template (Ollama warns on load).
- Two KDE sessions are running; the stale one holds integrated-graphics
  memory (`loginctl list-sessions`).
- The model card's sampling advice (temperature 0, repetition penalty 1.15)
  does not suit JSON output; a separate temperature test (0.5 against 0.6)
  could follow the model switch.
