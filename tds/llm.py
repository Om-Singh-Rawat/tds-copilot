"""OpenRouter chat client (stdlib only) with an on-disk response cache.

The cache keeps evaluation runs reproducible and saves free-tier quota:
the same prompt + model + temperature + sample index returns the stored reply.
"""
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


_cache_lock = threading.Lock()


def is_cached(messages: list[dict], model: str | None = None, temperature: float = 0.0, sample_idx: int = 0) -> bool:
    return _cache_path(messages, model or config.OPENROUTER_MODEL, temperature, sample_idx).exists()


def _cache_path(messages, model, temperature, sample_idx):
    key = hashlib.sha256(json.dumps([messages, model, temperature, sample_idx], sort_keys=True).encode()).hexdigest()
    return config.CACHE_DIR / f"{key}.json"


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.0,
         sample_idx: int = 0, use_cache: bool = True, max_retries: int = 4) -> dict:
    model = model or config.OPENROUTER_MODEL
    cache_file = _cache_path(messages, model, temperature, sample_idx)
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8")) | {"cached": True}

    if not config.LIVE_LLM:
        raise LLMError("live LLM calls are disabled on this server (TDS_LIVE_LLM=0); only cached answers are served")
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set (copy .env.example to .env)")

    body = json.dumps({"model": model, "messages": messages, "temperature": temperature}).encode()
    req = urllib.request.Request(config.OPENROUTER_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "tds-copilot-prototype",
    })

    delay = 5.0
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (429, 502, 503) and attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise LLMError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"Network error: {e.reason}") from e

    if "choices" not in data:
        raise LLMError(f"Unexpected response: {str(data)[:300]}")
    result = {
        "content": data["choices"][0]["message"]["content"] or "",
        "model": data.get("model", model),
        "cached": False,
    }
    with _cache_lock:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result
