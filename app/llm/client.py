"""Unified LLM caller. Tries providers in config order (groq, then gemini),
and within each provider, tries its configured models in order. Both
free-tier, no CC anywhere:
- Groq: https://console.groq.com (free key, no card)
- Google AI Studio (Gemini): https://aistudio.google.com/apikey (free key,
  no card — the Gemini API free tier has no expiry and no billing link;
  only upgrading to paid Cloud billing would ever ask for a card, and we
  never do that here)

Groq's current models (openai/gpt-oss-120b, openai/gpt-oss-20b) are
reasoning models — they think in a hidden chain-of-thought before
answering, and by default that leaks into the visible response as
<think>...</think> unless explicitly suppressed. reasoning_format="hidden"
in _call_groq is what turns that off; reasoning_effort="low" keeps the
hidden thinking itself short, since this is extraction work, not deep
problem-solving. https://console.groq.com/docs/reasoning
"""
import json
import re
import time
from app.config import get_config, get_secret

REQUEST_TIMEOUT_SECONDS = 30    # hard cap per call — a hung request must fail
                                 # fast and retry/fall-over, never hang indefinitely
MAX_RATE_LIMIT_WAIT_SECONDS = 65  # Groq's RPM window is 60s; cap how long we'll
                                    # ever wait on a single Retry-After
MAX_TOKENS = 4096               # generous headroom — even with reasoning hidden,
                                  # Groq still counts hidden reasoning tokens against
                                  # this budget, so too low a cap truncates the
                                  # answer before the model reaches its JSON output


class LLMError(Exception):
    pass


class _RateLimited(Exception):
    """Internal signal: this model is rate-limited right now. Caught by the
    retry loop so a 429 gets different handling than a real error — no point
    retrying the same model with a short sleep when the block is a per-minute
    quota; better to fall through to the next model/provider immediately."""
    def __init__(self, retry_after: float | None):
        self.retry_after = retry_after


def _call_groq(prompt: str, system: str, model: str, temperature: float) -> str:
    from groq import Groq
    import groq as groq_module

    client = Groq(api_key=get_secret("GROQ_API_KEY"), timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
            reasoning_effort="low",
            reasoning_format="hidden",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content
    except groq_module.RateLimitError as e:
        retry_after = None
        headers = getattr(getattr(e, "response", None), "headers", None)
        if headers:
            raw = headers.get("retry-after")
            if raw:
                try:
                    retry_after = float(raw)
                except ValueError:
                    pass
        raise _RateLimited(retry_after) from e


def _call_gemini(prompt: str, system: str, model: str, temperature: float) -> str:
    from google import genai
    from google.genai import types
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=get_secret("GEMINI_API_KEY"))
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=MAX_TOKENS,
            ),
        )
        return resp.text
    except genai_errors.ClientError as e:
        # Gemini free tier returns 429 RESOURCE_EXHAUSTED on RPM/RPD cap.
        # Check .code defensively — SDK versions vary in whether it's
        # reliably populated — falling back to string matching so a
        # rate limit is never mistaken for a hard failure.
        code = getattr(e, "code", None)
        if code == 429 or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            raise _RateLimited(None) from e
        raise


_PROVIDER_FN = {"groq": _call_groq, "gemini": _call_gemini}


def call_llm(prompt: str, system: str = "You are a precise data-extraction engine. Output only what is asked.") -> str:
    cfg = get_config()
    llm_cfg = cfg["llm"]
    providers = llm_cfg["provider_priority"]
    last_err = None

    for provider in providers:
        models = llm_cfg[provider]["model_priority"]
        fn = _PROVIDER_FN[provider]
        for model_idx, model in enumerate(models):
            is_last_model_overall = provider == providers[-1] and model_idx == len(models) - 1
            for attempt in range(llm_cfg["max_retries"]):
                try:
                    return fn(prompt, system, model, llm_cfg["temperature"])
                except _RateLimited as e:
                    last_err = e
                    if not is_last_model_overall:
                        # something else (another model, or another provider
                        # entirely) has its own separate quota — switch now
                        # rather than burning retries against a wall
                        break
                    wait = min(e.retry_after or 20, MAX_RATE_LIMIT_WAIT_SECONDS)
                    time.sleep(wait)
                except Exception as e:
                    last_err = e
                    time.sleep(1.5 * (attempt + 1))
            # this model's retries exhausted (or rate-limited and not last), fall through
    raise LLMError(f"All providers/models failed. Last error: {last_err}")


def call_llm_json(prompt: str, system: str = None) -> dict:
    sys_prompt = system or (
        "You are a precise data-extraction engine. "
        "Output ONLY valid JSON. No markdown fences, no commentary."
    )
    raw = call_llm(prompt, sys_prompt)
    cleaned = raw.strip()

    # Safety net: reasoning_format="hidden" should prevent this for Groq's
    # reasoning models, but if a <think> block leaks through anyway (a
    # future model swap, an API change), strip it rather than failing outright.
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    if cleaned.lower().startswith("<think>"):
        # unterminated block — the model ran out of tokens mid-thought and
        # never reached an answer. No JSON exists in this response at all;
        # fail clearly instead of trying to parse thinking-text as data.
        raise LLMError(
            "LLM response was cut off mid-reasoning before producing an answer "
            "(unterminated <think> block) — likely hit the token limit. "
            f"Raw: {raw[:300]}"
        )

    cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    if not cleaned.startswith("{"):
        # last resort: pull the first {...} object out of surrounding prose
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as strict_err:
        # LLMs occasionally produce almost-valid JSON — a missing closing
        # brace before the next sibling key is a real, observed failure mode
        # here (e.g. "mentions":[...]},"i":1,...  missing a "}" before the
        # comma). Rather than hand-patch that one shape, use json_repair,
        # a library built specifically for this class of LLM output error —
        # it fixes missing/extra brackets, commas, quotes, etc.
        try:
            import json_repair
            repaired = json_repair.loads(cleaned)
            if not isinstance(repaired, dict) or not repaired:
                # json_repair returns "" / {} / [] rather than raising when
                # the input is too broken to salvage — treat all of those,
                # and anything that isn't a dict, as failure too
                raise ValueError(f"json_repair could not recover a usable object (got: {repaired!r})")
            return repaired
        except Exception:
            raise LLMError(f"LLM did not return valid JSON: {strict_err}\nRaw: {raw[:500]}")