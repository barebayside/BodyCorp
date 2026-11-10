"""
A thin client for the Anthropic Messages API, using `requests` only (no SDK, to keep the
Catalyst function small). Used by ai.py (ai.make_client; tests replace it with a fake). Design:
docs/superpowers/specs/2026-11-10-ai-compliance-helper-design.md

WHAT IT DOES
    message(payload)          POST /v1/messages, synchronous. Used for everyday committee
                              questions on Haiku (must finish inside Catalyst's 30-second limit).
    create_batch(requests)    POST /v1/messages/batches. Used for by-law reviews on Sonnet and for
                              questions escalated to Sonnet: half price, no 30-second problem.
    get_batch(id)             GET  /v1/messages/batches/{id}: processing_status "in_progress" | "ended".
    batch_results(batch)      GET  the batch's results_url (JSON lines), as a list of dicts.

    cost_usd(model, usage, batch)   what a call cost, from the response's `usage`.
    aud(usd)                        converted at AI_AUD_PER_USD.

PRICES (US$ per million tokens), read 2026-11-10 from
https://platform.claude.com/docs/en/about-claude/pricing
    Claude Sonnet 5.5   input 2      5-min cache write 2.50   1-h cache write 4     cache hit 0.10   output 10
    Claude Haiku 5.5    input 0.10   5-min cache write 0.125  1-h cache write 0.20  cache hit 0.01   output 0.50
                        (a request whose prompt is OVER 100,000 tokens pays the higher row:
                         0.50 / 0.625 / 1 / 0.05 / 2.50, cache reads and writes included in the count)
    Batch API: 50% off input and output; the cache multipliers stack on top.
    Re-check this table when prices change; the cap depends on it.

ENVIRONMENT
    ANTHROPIC_API_KEY    the API key; unset means every call is refused (nothing is sent)
    AI_MONTHLY_CAP_AUD   the default monthly AI budget per building, in A$ (a building's
                         Settings.ai.monthly_cap_aud overrides it). Unset or 0 = AI is off.
    AI_AUD_PER_USD       A$ per US$1 for the budget sums. Default 1.60 (deliberately pessimistic,
                         not a looked-up rate).

HEADERS
    x-api-key, anthropic-version 2026-10-21 (the latest version, per
    https://platform.claude.com/docs/en/api/versioning: it refuses temperature/top_p/top_k, so we
    never send them). Catalyst only blocks an INCOMING Authorization header; this is outgoing.
"""

import json
import os

import requests

API = "https://api.anthropic.com/v1"
VERSION = "2026-10-21"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"

# US$ per million tokens.
PRICES = {
    SONNET: {"input": 2.0, "write_5m": 2.5, "write_1h": 4.0, "read": 0.10, "output": 10.0},
    HAIKU: {"input": 0.10, "write_5m": 0.125, "write_1h": 0.20, "read": 0.01, "output": 0.50},
}
HAIKU_LONG = {"input": 0.50, "write_5m": 0.625, "write_1h": 1.0, "read": 0.05, "output": 2.50}
HAIKU_LONG_OVER = 100000
BATCH_FACTOR = 0.5
DEFAULT_AUD_PER_USD = 1.60
SYNC_TIMEOUT = 25          # seconds; Catalyst kills the function at 30


class AiError(Exception):
    """A call that didn't work. `message` is safe to show; `retryable` says whether trying later may help."""

    def __init__(self, message, status=0, retryable=False):
        Exception.__init__(self, message)
        self.message = message
        self.status = status
        self.retryable = retryable


def _float_env(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


def aud_per_usd():
    return _float_env("AI_AUD_PER_USD", DEFAULT_AUD_PER_USD)


def aud(usd):
    return round(float(usd) * aud_per_usd(), 4)


def monthly_cap_aud(settings=None):
    """The building's cap: Settings.ai.monthly_cap_aud if set, else AI_MONTHLY_CAP_AUD. 0 = AI off."""
    ai = ((settings or {}).get("ai") or {}) if isinstance(settings, dict) else {}
    value = ai.get("monthly_cap_aud")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return _float_env("AI_MONTHLY_CAP_AUD", 0)


def usage_of(response):
    """The token counts of one Messages response (all ints, missing = 0)."""
    usage = (response or {}).get("usage") or {}
    split = usage.get("cache_creation") or {}
    write_1h = int(split.get("ephemeral_1h_input_tokens") or 0)
    write_total = int(usage.get("cache_creation_input_tokens") or 0)
    return {"input": int(usage.get("input_tokens") or 0),
            "write_5m": max(write_total - write_1h, 0),
            "write_1h": write_1h,
            "read": int(usage.get("cache_read_input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0)}


def prices_for(model, prompt_tokens=0):
    if model == HAIKU and prompt_tokens > HAIKU_LONG_OVER:
        return HAIKU_LONG
    if model not in PRICES:
        raise AiError("Unknown model {}.".format(model))
    return PRICES[model]


def cost_usd(model, usage, batch=False):
    """US$ for one call. `usage` is usage_of(...). Haiku's prompt length counts cache reads and writes."""
    prompt = usage["input"] + usage["write_5m"] + usage["write_1h"] + usage["read"]
    rate = prices_for(model, prompt)
    total = sum(usage[k] * rate[k] for k in ("input", "write_5m", "write_1h", "read", "output")) / 1e6
    return round(total * (BATCH_FACTOR if batch else 1.0), 6)


class Client:
    """
    The real client. Tests hand ai_review a fake with the same three-and-a-bit methods instead.
    `http` is anything with requests' post/get (a requests.Session, or the module).
    """

    def __init__(self, api_key=None, http=None, timeout=SYNC_TIMEOUT):
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.http = http or requests
        self.timeout = timeout

    def _headers(self):
        if not self.api_key:
            raise AiError("The AI helper isn't set up for this portal yet (no API key).", 0, False)
        return {"x-api-key": self.api_key, "anthropic-version": VERSION, "content-type": "application/json"}

    def _answer(self, resp):
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400:
            kind = ((body.get("error") or {}).get("type") or "") if isinstance(body, dict) else ""
            retryable = resp.status_code in (429, 500, 502, 503, 504, 529)
            raise AiError("The AI service said no ({} {}).".format(resp.status_code, kind).strip(),
                          resp.status_code, retryable)
        return body

    def _call(self, method, url, body=None, timeout=None):
        try:
            if method == "POST":
                resp = self.http.post(url, headers=self._headers(), data=json.dumps(body),
                                      timeout=timeout or self.timeout)
            else:
                resp = self.http.get(url, headers=self._headers(), timeout=timeout or self.timeout)
        except requests.exceptions.Timeout:
            raise AiError("The AI service took too long to answer.", 0, True)
        except requests.exceptions.RequestException:
            raise AiError("The AI service couldn't be reached.", 0, True)
        return resp

    def message(self, payload):
        return self._answer(self._call("POST", API + "/messages", payload))

    def create_batch(self, batch_requests):
        """batch_requests: [{"custom_id": "...", "params": <a Messages payload>}]"""
        return self._answer(self._call("POST", API + "/messages/batches", {"requests": batch_requests}))

    def get_batch(self, batch_id):
        return self._answer(self._call("GET", API + "/messages/batches/" + str(batch_id)))

    def batch_results(self, batch):
        """The ended batch's results, one dict per request: {custom_id, result: {type, message?}}."""
        url = (batch or {}).get("results_url")
        if not url:
            raise AiError("That batch has no results yet.")
        resp = self._call("GET", url, timeout=self.timeout)
        if resp.status_code >= 400:
            self._answer(resp)
        return [json.loads(line) for line in resp.text.splitlines() if line.strip()]
