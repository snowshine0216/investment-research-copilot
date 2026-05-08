"""Minimal OpenRouter connectivity diagnostic.

Runs two checks against the OpenRouter API to isolate where 403/401 errors
originate:

  1. GET /api/v1/auth/key      — verifies the API key itself (no token cost)
  2. POST /api/v1/chat/completions — verifies access to the configured
                                     memo_synthesis model (1-token request)

Usage:  uv run python scripts/check_openrouter.py
"""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv


BASE_URL = "https://openrouter.ai/api/v1"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm.yaml"


def _load_model_from_config() -> str:
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    return cfg["tasks"]["memo_synthesis"]["model"]


def _print_result(label: str, resp: httpx.Response) -> None:
    print(f"  status:  {resp.status_code} {resp.reason_phrase}")
    rate_limit = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-ratelimit")}
    if rate_limit:
        print(f"  rate:    {rate_limit}")
    try:
        body = resp.json()
        print(f"  body:    {json.dumps(body, indent=2)[:800]}")
    except ValueError:
        print(f"  body:    {resp.text[:800]}")
    print(f"  → {label}: {'PASS' if resp.is_success else 'FAIL'}")


def check_auth_key(client: httpx.Client, headers: dict[str, str]) -> bool:
    print("\n[1/2] GET /auth/key (verifies API key)")
    resp = client.get(f"{BASE_URL}/auth/key", headers=headers, timeout=15)
    _print_result("auth_key", resp)
    return resp.is_success


def check_chat_completion(client: httpx.Client, headers: dict[str, str], model: str) -> bool:
    print(f"\n[2/2] POST /chat/completions (verifies access to {model})")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    resp = client.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=30)
    _print_result("chat_completion", resp)
    return resp.is_success


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("FAIL: OPENROUTER_API_KEY missing from environment / .env")
        return 1

    print(f"Key prefix: {api_key[:10]}... (length={len(api_key)})")
    model = _load_model_from_config()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client() as client:
        auth_ok = check_auth_key(client, headers)
        chat_ok = check_chat_completion(client, headers, model)

    print("\n" + "=" * 50)
    if auth_ok and chat_ok:
        print("RESULT: OpenRouter connection healthy.")
        return 0
    if not auth_ok:
        print("RESULT: API key rejected. Check https://openrouter.ai/keys")
        return 2
    print(f"RESULT: Key valid, but model '{model}' inaccessible.")
    print("        Likely: insufficient credits, model gating, or geo-restriction.")
    print("        Check https://openrouter.ai/credits and the model page.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
