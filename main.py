# ============================================================
# NEW ONBOARDING ENDPOINTS
# ============================================================

class StrategyRequest(BaseModel):
    member_id: str
    stage: str
    bottleneck: str
    hours: str

class CompleteOnboardingRequest(BaseModel):
    member_id: str
    stage: str
    bottleneck: str
    hours: str
    strategy_document: str
    starting_day: int
    speed_profile: str

@app.post("/api/generate-strategy")
def generate_strategy(req: StrategyRequest):
    """Generate AI strategy document based on quiz answers"""
    
    # Calculate starting day
    starting_day = 1
    if req.stage == "product":
        starting_day = 15
    elif req.stage == "selling":
        starting_day = 31
    
    # Determine speed profile
    if req.hours == "8+":
        speed_profile = "accelerator"
    elif req.hours == "4-7":
        speed_profile = "steady"
    else:
        speed_profile = "reflective"
    
    # Map bottleneck to focus area
    bottleneck_map = {
        "traffic": "Module 3 — Attract (Content Engine)",
        "conversion": "Module 4 — Convert (Funnel Engineering)",
        "content": "Module 3 — Attract (Content Creation)",
        "community": "Module 5 — Automate (Community Systems)",
        "offer": "Module 2 — Package (Offer Engineering)",
        "time": "Module 5 — Automate (Systems)",
        "other": "Module 1 — Position (Foundation)"
    }
    focus = bottleneck_map.get(req.bottleneck, "Module 1 — Position")
    
    # Generate strategy document using AI
    system_prompt = """You are a strategic business coach. Generate a personalized strategy document based on the member's answers.

The document must include:
1. Current Stage (based on their answer)
2. Biggest Challenge (based on their answer)
3. Recommended Focus Area (based on their bottleneck)
4. Starting Day (calculated)
5. Speed Profile (based on hours)
6. Recommended First Task
7. Next Steps for the member

Use a clear, professional, and encouraging tone. The document should help the member understand their starting point and what to do next."""

    user_prompt = f"""Member answers:
- Stage: {req.stage}
- Biggest Challenge: {req.bottleneck}
- Hours Available: {req.hours}/week

Calculated:
- Starting Day: {starting_day}
- Speed Profile: {speed_profile}
- Focus Area: {focus}

Generate a strategy document."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    document = call_llm(messages)
    
    # Save to Supabase
    try:
        supabase.table("strategy_docs").insert({
            "member_id": req.member_id,
            "document": document,
            "starting_day": starting_day,
            "speed_profile": speed_profile,
            "bottleneck": req.bottleneck
        }).execute()
    except Exception as e:
        log.error(f"Error saving strategy doc: {e}")
    
    return {
        "document": document,
        "starting_day": starting_day,
        "speed_profile": speed_profile,
        "focus": focus
    }

@app.post("/api/complete-onboarding")
def complete_onboarding(req: CompleteOnboardingRequest):
    """Complete onboarding and setup journey"""
    
    # Get or create profile
    profile = db_get_profile(req.member_id)
    if not profile:
        db_upsert_profile(req.member_id, {
            "business_name": "New Member",
            "niche": "",
            "target_avatar": "",
            "biggest_bottleneck": req.bottleneck,
            "current_level": req.stage,
            "weekly_hours": req.hours,
            "speed_profile": req.speed_profile,
            "onboarding_complete": True
        })
    else:
        db_upsert_profile(req.member_id, {
            **profile,
            "current_level": req.stage,
            "weekly_hours": req.hours,
            "speed_profile": req.speed_profile,
            "onboarding_complete": True,
            "biggest_bottleneck": req.bottleneck
        })
    
    # Update or create journey
    journey = db_get_journey(req.member_id)
    if not journey:
        journey = {
            "member_id": req.member_id,
            "current_day": req.starting_day,
            "current_phase": "Phase 1",
            "current_task_id": "p1_t1",
            "tasks_completed": [],
            "streak": 0,
            "last_standup_date": None,
            "xp_total": 0,
            "badges": []
        }
    else:
        journey["current_day"] = req.starting_day
    
    db_upsert_journey(req.member_id, journey)
    
    # Save strategy document
    try:
        supabase.table("strategy_docs").upsert({
            "member_id": req.member_id,
            "document": req.strategy_document,
            "starting_day": req.starting_day,
            "speed_profile": req.speed_profile,
            "bottleneck": req.bottleneck
        }).execute()
    except Exception as e:
        log.error(f"Error saving strategy doc: {e}")
    
    return {
        "success": True,
        "message": "Onboarding complete",
        "starting_day": req.starting_day,
        "speed_profile": req.speed_profile
    }

@app.post("/api/upload-proof")
async def upload_proof(member_id: str, file: UploadFile = File(...)):
    """Upload proof file (screenshot, document)"""
    
    # Create member directory
    import os
    upload_dir = f"proofs/{member_id}"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    file_path = f"{upload_dir}/{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Save to Supabase
    try:
        supabase.table("proof_files").insert({
            "member_id": member_id,
            "filename": file.filename,
            "filepath": file_path,
            "file_type": file.content_type
        }).execute()
    except Exception as e:
        log.error(f"Error saving proof file: {e}")
    
    return {"success": True, "filename": file.filename}
