# ==============================================================================
# 🌌 GOOGOL-PLEX UPGRADE: MULTI-AGENT ORCHESTRATION ENGINES
# ==============================================================================

# 1. THE OMNI-FRAMEWORK MASTER PROMPT
OMNI_BRAIN = """
You are the E5 AI Coach Omni-Engine. You do not just answer questions; you cross-reference the user's input against ALL core frameworks simultaneously to provide a synthesized, hyper-leveraged Master Prescription.

CORE FRAMEWORKS TO CROSS-REFERENCE:
1. $100M Offers: Value Equation, Grand Slam, Scarcity, Urgency, Bonuses, Guarantees.
2. $100M Leads: Core 4, Rule of 100, Open to Goal, Lead Getters.
3. $100M Money Models: Attraction, Upsell, Downsell, Continuity.
4. $100M Retention: 5 Horsemen (Track attendance, Reach out 2x/week, Handwritten cards, Member events, Exit interviews), Activation Points.
5. $100M Closing: Transfer of power, overcoming blame (Circumstances, Other People, Self), All-Purpose Closes.
6. $100M Hooks: 70-20-10 rule, verbal/nonverbal hooks, testing.
7. TTB: Straight Line, One Group Hub, Paths > Libraries, Preselling.
8. AVOCADO: ECAFI (Engage, Connect, Assess, Frame, Invite), SOULFUL scripts, R.I.P.E. lead magnets.

YOUR OUTPUT FORMAT (The Master Prescription):
- 🎯 THE DIAGNOSIS: Which specific framework is the root cause? (e.g., "Your churn is high because you're ignoring the 5 Horsemen of Retention.")
- ⚡ THE PRESCRIPTION: The exact, step-by-step fix using the frameworks.
- 📝 THE ASSET: Generate the exact asset needed right now (e.g., an ECAFI win-back DM script, a Value Equation breakdown, or a Rule of 100 hook).
- ❓ THE PIERCING QUESTION: One high-leverage question to keep them moving.

NO FLUFF. NO GENERIC ADVICE. ONLY FRAMEWORK-BACKED, ACTIONABLE PRECISION.
"""

class OmniAuditRequest(BaseModel):
    member_id: str = "default"
    current_leads_per_month: int
    close_rate_percent: float
    average_ltv: float
    churn_rate_percent: float
    biggest_pain_point: str

@app.post("/api/omni-audit")
def omni_audit(req: OmniAuditRequest):
    """Predictive Money Model & Framework Oracle"""
    prompt = f"""
    User Metrics:
    - Leads/mo: {req.current_leads_per_month}
    - Close Rate: {req.close_rate_percent}%
    - Avg LTV: ${req.average_ltv}
    - Churn: {req.churn_rate_percent}%
    - Stated Pain Point: {req.biggest_pain_point}
    
    Run the Omni-Framework Cross-Pollinator. Diagnose the exact bottleneck using the $100M frameworks and provide the Master Prescription.
    """
    messages = [{"role": "system", "content": OMNI_BRAIN}, {"role": "user", "content": prompt}]
    try:
        result = post_process(call_llm(messages, temperature=0.3)) # Lower temp for precise auditing
        return {"audit": result}
    except Exception as e:
        raise HTTPException(500, f"Audit failed: {str(e)}")


class Daily100Request(BaseModel):
    member_id: str = "default"
    current_stage: str # e.g., "Lead Gen", "Scaling", "Retention"
    niche: str

@app.post("/api/daily-100")
def generate_daily_100(req: Daily100Request):
    """Autonomous Rule of 100 Task Generator"""
    prompt = f"""
    Generate a hyper-personalized "Rule of 100" Daily Action Plan for a {req.niche} business currently in the "{req.current_stage}" stage.
    
    Rules:
    1. Must total 100 primary actions (e.g., 50 DMs, 30 mins content, 20 follow-ups).
    2. Include 1 specific, ready-to-use Hook (from $100M Hooks).
    3. Include 1 specific, ready-to-use DM script (using AVOCADO ECAFI).
    4. Format clearly with checkboxes.
    """
    messages = [{"role": "system", "content": OMNI_BRAIN}, {"role": "user", "content": prompt}]
    try:
        result = post_process(call_llm(messages, temperature=0.7))
        return {"daily_plan": result}
    except Exception as e:
        raise HTTPException(500, f"Daily 100 generation failed: {str(e)}")


class RoleplayRequest(BaseModel):
    member_id: str = "default"
    user_message: str
    scenario: str # e.g., "Price Objection", "Need to think about it"

@app.post("/api/roleplay")
def closing_roleplay(req: RoleplayRequest):
    """Interactive Closing Playbook Simulator"""
    prompt = f"""
    You are a skeptical prospect in a sales call. The scenario is: "{req.scenario}".
    The user (salesperson) just said: "{req.user_message}".
    
    Your goal: Respond exactly as a skeptical prospect would, using the "Blame" frameworks from the $100M Closing Playbook (blaming circumstances, other people, or self). 
    After responding, add a hidden "[COACH GRADE: X/10]" evaluating if the user's last message effectively transferred power and overcame the objection, and suggest a better "All-Purpose Close" they could have used.
    """
    messages = [{"role": "system", "content": "You are a skeptical prospect AND an expert sales coach evaluating the user's performance."}, {"role": "user", "content": prompt}]
    try:
        result = post_process(call_llm(messages, temperature=0.8))
        return {"roleplay_response": result}
    except Exception as e:
        raise HTTPException(500, f"Roleplay failed: {str(e)}")
