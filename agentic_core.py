# agentic_core.py — 3-Layer Agentic Core
import os
from openai import OpenAI

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

_client = None
_groq_client = None
def _get_groq():
    global _groq_client
    if _groq_client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key: raise ValueError("GROQ_API_KEY not set")
        from openai import OpenAI
        _groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key, timeout=60.0)
    return _groq_client


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY, timeout=180.0)
    return _client

FRAMEWORK_GRAPH = {
    "position": {"targeting": ["ICP Builder", "Avatar Recon", "Core Message Canvas"]},
    "package": {"offer": ["Perfect Offer Builder", "10 Pillars of Offer Doc", "Value Ladder Canvas"], "message": ["Core Message Canvas", "Million Dollar Message", "Story Selling"]},
    "attract": {"content": ["Content Cannon", "7 Content Types", "Hand Raiser Posts"], "lead_magnet": ["R.I.P.E. Formula", "3 Types of Lead Magnets"], "launch": ["3-Phase Launch Flow", "21-Day Launch Cycle"]},
    "convert": {"dm": ["ECAFI", "S.O.U.L.F.U.L.", "7-Scenario DM Playbook", "S.I.P.E.", "Buyer Signal Cheat Sheet"], "sales": ["Insight Call Script", "Objection Akido"], "funnel": ["CVJ Audit", "Step LTV Benchmark"]},
    "automate": {"community": ["One Group Audit Checklist", "MVC Build Sheets", "Ascension Map"], "nurture": ["Green to Ripe Sequence", "Milestones"]},
    "optimize": {"metrics": ["Growth Scorecard", "Big 3 Planning Canvas"], "psychology": ["System 1 vs System 2", "Loss Aversion"]},
}

CONSTITUTION = [
    "Must use plain everyday words and never name a framework, method, book or author",
    "Must reference the user's Business DNA when it is not 'not set'",
    "Must include at least one specific action under 20 minutes",
    "Must NOT use generic phrases: 'I hope this helps', 'in today's world', 'leverage', 'synergy', 'delve into'",
    "Must end with a clear next step or action",
]

# ===== BRICK F.3b: plain words in the Content drawer pipeline (same banned list as main.py BRICK F.3) =====
_F3B_FALLBACK = "Plain everyday words only. Never name a framework, method, book or author."


def _f3b_plain_rule():
    # main.py imports this module, so main is already loaded: read its rule, never import it again.
    import sys
    for name in ("main", "__main__"):
        fn = getattr(sys.modules.get(name), "_f3_plain_rule", None)
        if callable(fn):
            try:
                return str(fn())
            except Exception:
                break
    return _F3B_FALLBACK
# ===== end BRICK F.3b =====


def _call(system, user, max_tokens=2000, temperature=0.5):
    # Try Groq first (fast)
    try:
        resp = _get_groq().chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if resp.choices:
            ct = resp.choices[0].message.content
            if ct: return ct.strip()
    except Exception as e:
        print(f"[AGENT] Groq failed: {e}. Falling back to NVIDIA.", flush=True)
    # Fallback: NVIDIA
    try:
        resp = _get_client().chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not resp.choices: return ""
        ct = resp.choices[0].message.content
        return ct.strip() if ct else ""
    except Exception as e2:
        return f"__ERROR__{e2}"

def diagnose(user_prompt):
    system = "You are a Diagnostic Agent. Read the user message and output ONE line in EXACTLY this format, no other text: STAGE=convert | CATEGORY=dm | BOTTLENECK=low dm replies. Choose STAGE from: position, package, attract, convert, automate, optimize. Choose CATEGORY from: targeting, offer, message, content, lead_magnet, launch, dm, sales, funnel, community, nurture, metrics, psychology."
    return _call(system, user_prompt, max_tokens=200, temperature=0.2)

def select_frameworks(diagnosis):
    if not diagnosis or "STAGE=" not in diagnosis:
        diagnosis = "STAGE=convert | CATEGORY=dm | BOTTLENECK=unknown"
    stage, category = "convert", "dm"
    for part in diagnosis.split("|"):
        p = part.strip()
        if p.startswith("STAGE="): stage = p.split("=", 1)[1].strip().lower()
        elif p.startswith("CATEGORY="): category = p.split("=", 1)[1].strip().lower()
    stage_map = FRAMEWORK_GRAPH.get(stage, {})
    return stage_map.get(category) or next(iter(stage_map.values()), ["ECAFI"])

def execute(user_prompt, frameworks, business_dna):
    system = f"You are an elite business coach. Business DNA: {business_dna}. {_f3b_plain_rule()} Be specific with numbers. Every action under 20 minutes. End with a clear next step."
    return _call(system, user_prompt, max_tokens=4000, temperature=0.6)

def critique_and_fix(user_prompt, frameworks, business_dna, draft):
    rules = "\n".join(f"- {r}" for r in CONSTITUTION)
    system = f"You are a strict Constitutional Critic. Check the DRAFT against the RULES. If ANY rule is violated, rewrite it. Output ONLY the final version, no commentary.\n\nRULES:\n{rules}"
    user = f"Business DNA: {business_dna}\n\nDRAFT:\n{draft}"
    return _call(system, user, max_tokens=4000, temperature=0.4)


# === FAST LOCAL FRAMEWORK SELECTOR (no AI call) ===
def select_by_keywords(user_prompt):
    p = user_prompt.lower()
    if any(w in p for w in ["dm", "message", "reply", "replies", "outreach", "inbox"]):
        return "convert", "dm", ["ECAFI", "S.O.U.L.F.U.L.", "7-Scenario DM Playbook", "S.I.P.E.", "Buyer Signal Cheat Sheet"]
    if any(w in p for w in ["offer", "pricing", "package", "price"]):
        return "package", "offer", ["Perfect Offer Builder", "10 Pillars of Offer Doc", "Value Ladder Canvas"]
    if any(w in p for w in ["content", "post", "video", "reel", "hook"]):
        return "attract", "content", ["Content Cannon", "7 Content Types", "Hand Raiser Posts"]
    if any(w in p for w in ["community", "group", "engagement", "members"]):
        return "automate", "community", ["One Group Audit Checklist", "MVC Build Sheets", "Ascension Map"]
    if any(w in p for w in ["launch", "webinar", "challenge", "waitlist"]):
        return "attract", "launch", ["3-Phase Launch Flow", "21-Day Launch Cycle", "5-Day Challenge"]
    if any(w in p for w in ["funnel", "conversion", "bottleneck", "ltv"]):
        return "convert", "funnel", ["CVJ Audit", "Step LTV Benchmark", "Bottleneck Hunter"]
    if any(w in p for w in ["icp", "avatar", "audience", "target"]):
        return "position", "targeting", ["ICP Builder", "Avatar Recon", "Core Message Canvas"]
    return "convert", "dm", ["ECAFI", "S.O.U.L.F.U.L.", "Buyer Signal Cheat Sheet"]


# === SINGLE-CALL PIPELINE (fast, reliable) ===
def agentic_pipeline(user_prompt, business_dna="not set"):
    from knowledge_loader import get_context
    import time

    # === AGENT 1: DIAGNOSTICIAN ===
    t0 = time.time()
    # BRICK F.3b: diagnose() removed: select_by_keywords() handles
    # routing. Saves one AI call per Content drawer request.
    diagnosis = "STAGE=convert | CATEGORY=dm | BOTTLENECK=unknown"
    stage, category, frameworks = select_by_keywords(user_prompt)
    fw_list = ", ".join(frameworks)
    rules = " | ".join(CONSTITUTION)
    print(f"[AGENT] Step 1 Diagnose: {time.time()-t0:.1f}s", flush=True)

    # === AGENT 2: EXECUTOR ===
    t1 = time.time()
    knowledge_ctx = get_context(user_prompt, top_k=3, max_chars_per_file=2500)
    system_exec = (
        "You are an elite business coach. Ground every answer in the COACH NOTES below (use the ideas, never the names). "
        "Business DNA: " + business_dna + ". "
        + _f3b_plain_rule() + " Be specific with numbers. Every action under 20 minutes. "
        "End with a clear next step. "
        "RULES (violating any = failure): " + rules + "\n\n"
        "=== COACH NOTES (use the ideas, never the names) ===\n" + knowledge_ctx
    )
    draft = _call(system_exec, user_prompt, max_tokens=2500, temperature=0.5)
    if draft.startswith("__ERROR__"):
        print("[AGENT] ERROR: " + str(draft)[:500], flush=True)
        return {"ok": False, "error": "The AI could not answer right now. Please try again."}
    print(f"[AGENT] Step 2 Execute: {time.time()-t1:.1f}s", flush=True)

    # === AGENT 3: CRITIC ===
    t2 = time.time()
    rules_list = "\n".join(f"- {r}" for r in CONSTITUTION)
    system_critic = (
        "You are a strict Constitutional Critic. Check the DRAFT against the RULES. "
        "If ANY rule is violated (a framework, method, book or author named, generic phrases, no specific action, no next step), "
        "rewrite the draft to fix it. If all rules pass, output the draft unchanged. "
        "Output ONLY the final version. No commentary. No preamble.\n\n"
        "RULES:\n" + rules_list + "\n- " + _f3b_plain_rule()
    )
    user_critic = "Business DNA: " + business_dna + "\n\nDRAFT:\n" + draft
    final = _call(system_critic, user_critic, max_tokens=2500, temperature=0.3)
    if final.startswith("__ERROR__"):
        final = draft
    print(f"[AGENT] Step 3 Critic: {time.time()-t2:.1f}s", flush=True)
    print(f"[AGENT] TOTAL: {time.time()-t0:.1f}s", flush=True)

    return {
        "ok": True,
        "text": final,
        "model": "agentic-3agent-v1",
        "stage": stage,
        "category": category,
        "frameworks": [],  # BRICK F.3b: names stay on the server
    }
