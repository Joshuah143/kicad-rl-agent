"""Design-intake chatbot: a Claude-style conversation that gathers a structured
circuit brief, then hands it to the kicad-rl-8b policy to generate the design.

The conversation model (``claude-sonnet-4-5``) runs through the HUD gateway and
is instructed to ALWAYS answer with a strict JSON object carrying both a
human-facing ``reply`` and a structured ``brief``. We render ``reply`` as a chat
bubble and mirror ``brief`` into a live "Design brief" panel. When the brief is
complete, the brief becomes a :class:`TaskSpec` and the existing rollout pipeline
generates + scores the circuit with kicad-rl-8b.
"""

from __future__ import annotations

import json
import re
from typing import Optional

CHAT_MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """\
You are a senior hardware engineer running a friendly, efficient design intake
for a PCB-design AI. Your job is to interview the user and converge on a precise,
buildable circuit brief.

Behaviour:
- Ask ONE focused clarifying question per turn (like a real chat). Be concise.
- Cover, over the conversation: what the circuit must do; supply voltage/current;
  key interfaces or parts (e.g. connectors, ICs, sensors, protocol); package
  preference (through-hole THT vs surface-mount SMD); and any size or cost limits.
- Infer sensible defaults rather than over-asking; do not interrogate. Three to
  five good questions is usually enough.
- When you have enough to design something concrete, set "ready" to true and give
  a short confirming summary in "reply".

Output format: respond with ONLY a single JSON object (no prose, no markdown
fences) of exactly this shape:
{
  "reply": "<your conversational message to the user>",
  "clarifying_question": "<the one question you are asking, or empty if ready>",
  "ready": <true|false>,
  "brief": {
    "title": "<short snake_case name, e.g. usb_c_5v_led>",
    "description": "<one sentence>",
    "requirements": ["<concrete requirement>", "..."],
    "package_type": "<SMD|THT|null>",
    "max_cost_usd": <number|null>,
    "max_area_mm2": <number|null>
  }
}
Always include the full "brief" object, carrying forward everything agreed so far
(do not drop earlier fields). Keep requirements specific and testable.
"""

DEFAULT_BRIEF: dict = {
    "title": "",
    "description": "",
    "requirements": [],
    "package_type": None,
    "max_cost_usd": None,
    "max_area_mm2": None,
}

GREETING = (
    "Hi! I'll help you design a circuit. Tell me what you want to build "
    "and roughly what it should do, and I'll ask a few quick questions to nail "
    "down the details."
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    if not text:
        return ""
    cleaned = _THINK_RE.sub("", text)
    low = cleaned.lower()
    if "<think>" in low and "</think>" not in low:
        cleaned = cleaned[: low.index("<think>")]
    return cleaned.strip()


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object from a model reply, tolerating fences/prose."""
    if not text:
        return None
    s = _strip_think(text).strip()
    # Strip a ```json ... ``` fence if present.
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    # Fast path.
    try:
        return json.loads(s)
    except Exception:
        pass
    # Fallback: first balanced {...} span.
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except Exception:
                    return None
    return None


def _merge_brief(prev: dict, new: Optional[dict]) -> dict:
    """Merge a freshly parsed brief over the previous one, keeping known fields."""
    out = dict(DEFAULT_BRIEF)
    out.update({k: v for k, v in (prev or {}).items() if k in DEFAULT_BRIEF})
    if new:
        for k in DEFAULT_BRIEF:
            v = new.get(k)
            if v not in (None, "", []):
                out[k] = v
    return out


def run_chat_turn(history: list[dict], prev_brief: dict, settings) -> dict:
    """Send the conversation to the chat model and parse a structured turn.

    Parameters
    ----------
    history:
        List of ``{"role": "user"|"assistant", "content": str}`` messages.
    prev_brief:
        The brief gathered so far (merged forward).
    settings:
        Runtime settings carrying the HUD gateway key/url.

    Returns a dict ``{"reply": str, "ready": bool, "brief": dict}``.
    """
    from circuit_agent.infra.fireworks_client import FireworksClient

    client = FireworksClient.from_hud(settings)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend({"role": m["role"], "content": m["content"]} for m in history)

    completions = client.chat(
        CHAT_MODEL, messages, temperature=0.4, max_tokens=1200, n=1
    )
    raw = completions[0] if completions else ""
    parsed = _extract_json(raw)

    if not parsed:
        # Graceful fallback: treat the whole thing as a plain reply.
        return {
            "reply": _strip_think(raw) or "Sorry, could you rephrase that?",
            "ready": False,
            "brief": _merge_brief(prev_brief, None),
        }

    brief = _merge_brief(prev_brief, parsed.get("brief"))
    reply = (parsed.get("reply") or "").strip()
    if not reply:
        reply = parsed.get("clarifying_question") or "Could you tell me a bit more?"
    return {"reply": reply, "ready": bool(parsed.get("ready")), "brief": brief}


def _safe_name(title: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", (title or "").strip()).strip("_")
    return base.lower() or "custom_design"


def brief_to_taskspec(brief: dict):
    """Convert a gathered brief into a :class:`circuit_agent.task.TaskSpec`."""
    from circuit_agent.task import Preferences, TaskSpec

    pkg = brief.get("package_type")
    pkg = pkg.upper() if isinstance(pkg, str) and pkg.strip() else None
    if pkg not in ("SMD", "THT"):
        pkg = None

    prefs = Preferences(
        package_type=pkg,
        max_bom_cost_usd=_as_float(brief.get("max_cost_usd")),
        max_area_mm2=_as_float(brief.get("max_area_mm2")),
    )
    reqs = [str(r).strip() for r in (brief.get("requirements") or []) if str(r).strip()]
    return TaskSpec(
        name=_safe_name(brief.get("title") or brief.get("description")),
        description=str(brief.get("description") or "").strip(),
        requirements=reqs,
        preferences=prefs,
    )


def _as_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def brief_is_ready(brief: dict) -> bool:
    """A brief is generatable once it has a description and >=1 requirement."""
    return bool(str(brief.get("description") or "").strip()
                and (brief.get("requirements") or []))


# Keyword weights for matching a free-form brief to one of the five reference
# designs (used by the reliable "Demo" generation mode). Each design has a
# matching tasks/<name>.yaml and a known-good program in dsl.examples.
REFERENCE_KEYWORDS: dict[str, list[str]] = {
    "usb_c_5v_led": ["usb-c", "usb c", "usb", "type-c", "type c", "vbus", "5v",
                     "power led", "power indicator", "indicator", "led"],
    "led_resistor": ["led", "resistor", "current limit", "blink", "indicator", "diode"],
    "ldo_3v3": ["ldo", "regulator", "3.3", "3v3", "3.3v", "voltage regulator",
                "step down", "step-down", "linear regulator", "power supply"],
    "i2c_sensor_breakout": ["i2c", "sensor", "sda", "scl", "breakout", "pullup",
                            "pull-up", "temperature", "imu", "accelerometer"],
    "mcu_minimal": ["mcu", "microcontroller", "stm32", "processor", "cpu",
                    "reset", "decoupling", "firmware", "gpio"],
}

DEFAULT_REFERENCE = "usb_c_5v_led"


def match_reference(brief: dict) -> str:
    """Pick the reference design that best matches a brief (keyword scoring).

    Returns one of the five reference design names; defaults to a rich, demo-
    friendly board when nothing matches strongly.
    """
    hay = " ".join([
        str(brief.get("title") or ""),
        str(brief.get("description") or ""),
        " ".join(str(r) for r in (brief.get("requirements") or [])),
    ]).lower()

    best, best_score = DEFAULT_REFERENCE, 0
    for name, words in REFERENCE_KEYWORDS.items():
        score = sum(hay.count(w) for w in words)
        if score > best_score:
            best, best_score = name, score
    return best


__all__ = [
    "CHAT_MODEL",
    "SYSTEM_PROMPT",
    "DEFAULT_BRIEF",
    "GREETING",
    "run_chat_turn",
    "brief_to_taskspec",
    "brief_is_ready",
    "match_reference",
    "REFERENCE_KEYWORDS",
    "DEFAULT_REFERENCE",
]
