#!/usr/bin/env python3
"""Brick 4 backend for main.py: POST /api/first-win/draft and POST /api/first-win.

Usage (run in /root/e5-ai-coach):
  python3 patch_brick4_backend.py --check   dry run: verify every anchor, write nothing
  python3 patch_brick4_backend.py           apply (backup: main.py.bak-brick4)

Requires Brick 1B backend. Refuses to run twice.
This file contains no angle brackets or ampersands: they are written as escapes.
"""
import os, shutil, sys

PATH = "main.py"
MARK = "BRICK 4: FIRST WIN"
NEEDS = "BRICK 1B: WORKSPACE SYNC"
NEEDS_MSG = "Brick 1B backend is not applied. Run patch_brick1b.py first."
BACKUP = PATH + ".bak-brick4"
COMPILE = True

EDITS = [
    ("Brick 4 backend block after Brick 1B",
     "# ===== end BRICK 1B backend =====",
     "# ===== end BRICK 1B backend =====\n\n\n# ============================================================\n# BRICK 4: FIRST WIN (10-minute first task: offer, 3 outcomes, price, guarantee)\n# POST /api/first-win/draft  AI drafts all four parts (counts against the AI quota)\n# POST /api/first-win        saves them and completes task p1_t1 in one locked transaction\n# Silent by design: after require_member, every failure is {\"ok\": False, \"reason\": ...} with HTTP 200.\n# Does not add 7 days, does not touch the streak, writes no standup or score row.\n# ============================================================\nfrom integration_support import check_rate_limit as _fw_rate_check\n\nFW_TASK_ID = \"p1_t1\"\nFW_XP = 125\nFW_MAX_BODY_BYTES = 32 * 1024\nFW_WHERE = {\"youtube\": \"content\", \"dms\": \"outbound\", \"community\": \"community\", \"email\": \"email\"}\nFW_HOURS = (\"1-3\", \"4-7\", \"8+\")\nFW_SPEED = {\"1-3\": \"reflective\", \"4-7\": \"steady\", \"8+\": \"accelerator\"}\n\n\ndef _fw_text(value, max_len):\n    \"\"\"Single-line, trimmed, length-capped text. Non-strings become empty.\"\"\"\n    if not isinstance(value, str):\n        return \"\"\n    return \" \".join(value.split())[:max_len]\n\n\nasync def _fw_read(request):\n    try:\n        raw = await request.body()\n        if not raw or len(raw) \x3e FW_MAX_BODY_BYTES:\n            return None\n        data = json.loads(raw)\n        return data if isinstance(data, dict) else None\n    except Exception:\n        return None\n\n\ndef _fw_answers(raw):\n    a = raw if isinstance(raw, dict) else {}\n    out = {}\n    sell = _fw_text(a.get(\"sell\"), 300)\n    who = _fw_text(a.get(\"who\"), 300)\n    where = str(a.get(\"where\") or \"\").strip().lower()\n    hours = str(a.get(\"hours\") or \"\").strip()\n    if sell:\n        out[\"sell\"] = sell\n    if who:\n        out[\"who\"] = who\n    if where in FW_WHERE:\n        out[\"where\"] = where\n    if hours in FW_HOURS:\n        out[\"hours\"] = hours\n    return out\n\n\ndef _fw_outcomes(value):\n    items = value if isinstance(value, list) else []\n    return [x for x in (_fw_text(i, 200) for i in items) if x][:3]\n\n\ndef _fw_clean_win(body):\n    \"\"\"Returns (win, None) or (None, message). All four parts of p1_t1 are required.\"\"\"\n    offer = _fw_text(body.get(\"offer\"), 280)\n    outcomes = _fw_outcomes(body.get(\"outcomes\"))\n    price = _fw_text(body.get(\"price\"), 60)\n    guarantee = _fw_text(body.get(\"guarantee\"), 280)\n    if len(offer) \x3c 15:\n        return None, \"Write your offer in at least 15 characters.\"\n    if len(outcomes) != 3:\n        return None, \"Fill in all 3 results your customer gets.\"\n    if not price:\n        return None, \"Add a price. A guess is fine; you can change it later.\"\n    if not guarantee:\n        return None, \"Add a guarantee, even a simple one.\"\n    return {\"offer\": offer, \"outcomes\": outcomes, \"price\": price, \"guarantee\": guarantee}, None\n\n\ndef _fw_draft_messages(a):\n    where_label = {\"youtube\": \"YouTube or short videos\", \"dms\": \"direct messages\",\n                   \"community\": \"an online community\", \"email\": \"an email list\"}.get(a.get(\"where\", \"\"), \"not given\")\n    system = (\n        \"You help a beginner coach or creator write their first offer. \"\n        \"Write in the same language as their answers. Use plain, everyday words. \"\n        \"No framework names, no jargon, no hype, no income claims. \"\n        \"Return ONLY one JSON object, no markdown, no code fences, with exactly these keys: \"\n        '{\"offer\": \"one sentence: who it helps, the result, and how\", '\n        '\"outcomes\": [\"result 1\", \"result 2\", \"result 3\"], '\n        '\"price\": \"a realistic starting price with currency, e.g. $97\", '\n        '\"guarantee\": \"one simple, honest guarantee they can keep\"}. '\n        \"The JSON keys stay in English.\"\n    )\n    user = (\n        \"What I sell: \" + a.get(\"sell\", \"\") + \"\\n\"\n        \"Who it is for: \" + a.get(\"who\", \"\") + \"\\n\"\n        \"Where my audience is: \" + where_label + \"\\n\"\n        \"Hours per week I have: \" + a.get(\"hours\", \"not given\")\n    )\n    return [{\"role\": \"system\", \"content\": system}, {\"role\": \"user\", \"content\": user}]\n\n\ndef _fw_parse_draft(raw):\n    s = str(raw or \"\")\n    i, j = s.find(\"{\"), s.rfind(\"}\")\n    if i == -1 or j == -1 or j \x3c= i:\n        return None\n    try:\n        d = json.loads(s[i:j + 1])\n    except Exception:\n        return None\n    if not isinstance(d, dict):\n        return None\n    draft = {\"offer\": _fw_text(d.get(\"offer\"), 280), \"outcomes\": _fw_outcomes(d.get(\"outcomes\")),\n             \"price\": _fw_text(str(d.get(\"price\") or \"\"), 60), \"guarantee\": _fw_text(d.get(\"guarantee\"), 280)}\n    if not draft[\"offer\"] or len(draft[\"outcomes\"]) != 3 or not draft[\"price\"] or not draft[\"guarantee\"]:\n        return None\n    return draft\n\n\ndef _fw_commit(member_id, win, answers):\n    \"\"\"Complete p1_t1 and merge the profile in one transaction (journey row locked).\"\"\"\n    conn = _sync_conn()\n    if not conn:\n        return {\"ok\": False, \"reason\": \"db_unavailable\"}\n    try:\n        with conn:\n            with conn.cursor() as cur:\n                default = {\"current_day\": 1, \"current_phase\": \"Phase 1\", \"current_task_id\": FW_TASK_ID,\n                           \"tasks_completed\": [], \"streak\": 0, \"last_standup_date\": None, \"xp_total\": 0, \"badges\": []}\n                cur.execute(\"INSERT INTO journeys (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO NOTHING\",\n                            (member_id, json.dumps(default)))\n                cur.execute(\"SELECT data FROM journeys WHERE member_id = %s FOR UPDATE\", (member_id,))\n                row = cur.fetchone()\n                journey = dict(row[\"data\"]) if row and isinstance(row.get(\"data\"), dict) else dict(default)\n                completed = list(journey.get(\"tasks_completed\") or [])\n                if FW_TASK_ID in completed:\n                    return {\"ok\": False, \"reason\": \"already_done\"}\n                if journey.get(\"current_phase\", \"Phase 1\") != \"Phase 1\" or journey.get(\"current_task_id\", FW_TASK_ID) != FW_TASK_ID:\n                    return {\"ok\": False, \"reason\": \"wrong_task\"}\n                now = datetime.now().isoformat()\n                completed.append(FW_TASK_ID)\n                journey[\"tasks_completed\"] = completed\n                journey.setdefault(\"current_phase\", \"Phase 1\")\n                journey.setdefault(\"current_day\", 1)\n                advance_journey(journey, member_id)\n                journey[\"xp_total\"] = int(journey.get(\"xp_total\") or 0) + FW_XP\n                journey[\"first_win_at\"] = now\n                cur.execute(\"UPDATE journeys SET data = %s WHERE member_id = %s\", (json.dumps(journey), member_id))\n                cur.execute(\"SELECT data FROM profiles WHERE member_id = %s FOR UPDATE\", (member_id,))\n                prow = cur.fetchone()\n                profile = dict(prow[\"data\"]) if prow and isinstance(prow.get(\"data\"), dict) else {}\n                profile.update({\"core_offer\": win[\"offer\"], \"offer_outcomes\": win[\"outcomes\"],\n                                \"offer_price\": win[\"price\"], \"offer_guarantee\": win[\"guarantee\"],\n                                \"onboarding_complete\": True, \"first_win_at\": now})\n                if answers.get(\"sell\"):\n                    profile[\"offer_sells\"] = answers[\"sell\"]\n                    if not str(profile.get(\"niche\") or \"\").strip():\n                        profile[\"niche\"] = answers[\"sell\"]\n                if answers.get(\"who\"):\n                    profile[\"target_avatar\"] = answers[\"who\"]\n                if answers.get(\"where\"):\n                    profile[\"primary_traffic_source\"] = FW_WHERE[answers[\"where\"]]\n                    profile[\"audience_channel\"] = answers[\"where\"]\n                if answers.get(\"hours\"):\n                    profile[\"weekly_hours\"] = answers[\"hours\"]\n                    profile[\"speed_profile\"] = FW_SPEED[answers[\"hours\"]]\n                if not str(profile.get(\"business_name\") or \"\").strip():\n                    profile[\"business_name\"] = str(profile.get(\"name\") or \"\").strip() or \"New Member\"\n                profile.setdefault(\"current_level\", \"beginner\")\n                cur.execute(\"INSERT INTO profiles (member_id, data) VALUES (%s, %s) \"\n                            \"ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data\",\n                            (member_id, json.dumps(profile)))\n        return {\"ok\": True, \"task_unlocked\": True, \"task_id\": FW_TASK_ID, \"xp_gained\": FW_XP,\n                \"xp_total\": journey[\"xp_total\"], \"streak\": journey.get(\"streak\", 0),\n                \"next_task_id\": journey.get(\"current_task_id\")}\n    except Exception as e:\n        log.error(\"FirstWin: save failed: \" + str(e))\n        return {\"ok\": False, \"reason\": \"db_unavailable\"}\n    finally:\n        _sync_close(conn)\n\n\n@app.post(\"/api/first-win/draft\")\nasync def first_win_draft(request: Request):\n    member_id = require_member(request)  # outside try: 401 behaves like every other route\n    try:\n        body = await _fw_read(request)\n        if body is None:\n            return {\"ok\": False, \"reason\": \"invalid\"}\n        a = _fw_answers(body.get(\"answers\"))\n        if not a.get(\"sell\") or not a.get(\"who\"):\n            return {\"ok\": False, \"reason\": \"invalid\", \"detail\": \"Tell us what you sell and who it is for.\"}\n        session = getattr(request.state, \"session\", None) or {}\n        if not session.get(\"admin\"):\n            # Counted against the existing AI quota (20/min, 500/day) via an AI path it already covers.\n            if _fw_rate_check(member_id, \"/api/ai/generate\") is not None:\n                return {\"ok\": False, \"reason\": \"rate_limited\"}\n        raw = await run_in_threadpool(call_llm, _fw_draft_messages(a), 0.4, 900)\n        if not isinstance(raw, str) or not raw.strip() or raw.lstrip().lower().startswith(\"error:\"):\n            return {\"ok\": False, \"reason\": \"ai_unavailable\"}\n        draft = _fw_parse_draft(raw)\n        if not draft:\n            return {\"ok\": False, \"reason\": \"ai_bad_output\"}\n        return {\"ok\": True, \"draft\": draft}\n    except Exception as e:\n        log.error(\"FirstWin: draft failed: \" + str(e))\n        return {\"ok\": False, \"reason\": \"ai_unavailable\"}\n\n\n@app.post(\"/api/first-win\")\nasync def first_win_save(request: Request):\n    member_id = require_member(request)  # outside try: 401 behaves like every other route\n    try:\n        body = await _fw_read(request)\n        if body is None:\n            return {\"ok\": False, \"reason\": \"invalid\"}\n        if str(body.get(\"current_task_id\") or \"\") != FW_TASK_ID:\n            return {\"ok\": False, \"reason\": \"wrong_task\"}\n        win, err = _fw_clean_win(body)\n        if not win:\n            return {\"ok\": False, \"reason\": \"invalid\", \"detail\": err}\n        return await run_in_threadpool(_fw_commit, member_id, win, _fw_answers(body.get(\"answers\")))\n    except Exception as e:\n        log.error(\"FirstWin: save failed: \" + str(e))\n        return {\"ok\": False, \"reason\": \"error\"}\n# ===== end BRICK 4 backend ====="),
]


def main():
    check = "--check" in sys.argv
    if not os.path.exists(PATH):
        print("ABORTED: " + PATH + " not found in " + os.getcwd())
        sys.exit(1)
    src = open(PATH, encoding="utf-8").read()
    if MARK in src:
        print("ABORTED: this patch is already applied. Nothing written.")
        sys.exit(1)
    if NEEDS not in src:
        print("ABORTED: " + NEEDS_MSG)
        sys.exit(1)
    bad = []
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            bad.append(name + " (found " + str(n) + " times, expected 1)")
    if bad:
        print("ABORTED: anchors do not match. Nothing written.")
        for b in bad:
            print("  - " + b)
        sys.exit(1)
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    if MARK not in out:
        print("ABORTED: self-check failed. Nothing written.")
        sys.exit(1)
    if COMPILE:
        try:
            compile(out, PATH, "exec")
        except SyntaxError as e:
            print("ABORTED: patched file would not compile: " + str(e) + ". Nothing written.")
            sys.exit(1)
    if check:
        print("CHECK OK: all " + str(len(EDITS)) + " anchors found exactly once" + (" and the result compiles" if COMPILE else "") + ". Nothing written.")
        return
    shutil.copyfile(PATH, BACKUP)
    open(PATH, "w", encoding="utf-8").write(out)
    print("PATCHED: " + str(len(EDITS)) + " edit(s) applied. Backup: " + BACKUP)
    print("Next: docker compose down, then docker compose up -d --build" + ("" if COMPILE else ", then purge Cloudflare for /app"))


if __name__ == "__main__":
    main()
