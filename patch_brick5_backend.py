#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick 5 backend: beginner coach prompt for guided-mode users (main.py only).

Usage (run from /root/e5-ai-coach):
  python3 patch_brick5_backend.py --check   dry run: checks prerequisites and anchors, writes nothing
  python3 patch_brick5_backend.py           applies the patch (backup: main.py.bak-brick5)

Copy-safe: this file contains no less-than, greater-than or ampersand characters.
They are stored as tokens and rebuilt with chr() when the script runs:
  @@LT@@ is chr(60), @@GT@@ is chr(62), @@AMP@@ is chr(38)
"""
import shutil
import sys

TARGET = "main.py"
BACKUP = TARGET + ".bak-brick5"
MARKER = "BRICK 5: BEGINNER COACH PROMPT"
LT, GT, AMP = chr(60), chr(62), chr(38)


def dec(s):
    return s.replace("@@LT@@", LT).replace("@@GT@@", GT).replace("@@AMP@@", AMP)


PREREQS = [('Brick 1B', 'BRICK 1B'), ('Brick 4 (first win)', 'BRICK 4: FIRST WIN')]

# (name, old, new, expected_count)
EDITS = [
    ('ChatRequest beginner field', r'''class ChatRequest(BaseModel): message: str = Field(default="", max_length=20000); history: List[ChatMessage] = Field(default_factory=list, max_length=20); mode: str = "coach"; member_id: Optional[str] = "default"''', r'''class ChatRequest(BaseModel): message: str = Field(default="", max_length=20000); history: List[ChatMessage] = Field(default_factory=list, max_length=20); mode: str = "coach"; member_id: Optional[str] = "default"; beginner: bool = False''', 1),
    ('beginner prompt in /api/chat and /api/chat/stream', r'''    messages = [{"role": "system", "content": system_prompt}] + [{"role": m.role, "content": m.content} for m in req.history[-10:]] + [{"role": "user", "content": req.message}]''', r'''    system_prompt = _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context, standups_text, wins_full_text, system_prompt)
    messages = [{"role": "system", "content": system_prompt}] + [{"role": m.role, "content": m.content} for m in req.history[-10:]] + [{"role": "user", "content": req.message}]''', 2),
    ('Brick 5 helper block', r'''# ===== end BRICK 4 backend =====''', r'''# ===== end BRICK 4 backend =====

# ============================================================
# BRICK 5: BEGINNER COACH PROMPT (guided-mode users only)
# Used only when the request says beginner=true AND the server's journey has
# fewer than 2 completed tasks (the same rule as guided mode). Otherwise the
# original prompt is used, unchanged. Any error falls back to the original.
# ============================================================
import operator as _op5

B5_GUIDED_TASK_LIMIT = 2


def _b5_beginner_on(req, journey):
    try:
        if getattr(req, "beginner", False) is not True:
            return False
        done = journey.get("tasks_completed") if isinstance(journey, dict) else None
        return _op5.lt(len(done or []), B5_GUIDED_TASK_LIMIT)
    except Exception:
        return False


def _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context,
                      standups_text, wins_text, default_prompt):
    if not _b5_beginner_on(req, journey):
        return default_prompt
    try:
        N = chr(10)
        p = profile if isinstance(profile, dict) else {}
        t = current_task if isinstance(current_task, dict) else {}
        done = t.get("id") in (journey.get("tasks_completed") or [])
        dels = N.join("- " + str(d) for d in (t.get("deliverables") or []))
        return (
            "You are a warm, practical business coach talking to a beginner." + N + N +
            "LANGUAGE RULE: Always reply in the same language the user writes in. If Arabic, reply fully in Arabic. If English, reply in English." + N + N +
            "MEMBER: Sells: " + str(p.get("core_offer") or p.get("niche") or "not set yet") +
            " | Helps: " + str(p.get("target_avatar") or "not set yet") +
            " | Audience channel: " + str(p.get("primary_traffic_source", "content")) +
            " | Hours per week: " + str(p.get("weekly_hours", "not set")) + N +
            "Day: " + str(journey.get("current_day", 1)) + "/90 | Phase: " + str(phase_info.get("name", "")) +
            " | Current task: " + str(t.get("name", "")) +
            " | Status: " + ("completed" if done else "not completed yet") + N +
            "WHAT THE CURRENT TASK ASKS FOR:" + N + (dels or "- (nothing listed)") + N + N +
            "RECENT STANDUPS:" + N + str(standups_text) + N + N +
            "RECENT WINS:" + N + str(wins_text) + N + N +
            "BACKGROUND IDEAS (use the ideas if they help; never mention their names, authors, books or sources):" + N +
            (framework_context if framework_context else "None.") + N + N +
            "RULES:" + N +
            "1. Use plain, everyday words. No jargon, no acronyms, no framework names, no author or book names." + N +
            "2. Work on one part of the current task at a time." + N +
            "3. Give at most 3 numbered steps the user can do today." + N +
            "4. End with at most one short question." + N +
            "5. Keep it under about 150 words: a short paragraph, then the numbered steps. No headings." + N +
            "6. Always answer the user's question first. If it is off-task, answer briefly, then bring them back to the current task." + N +
            "7. Never invent facts about the user. Never promise income or results."
        )
    except Exception:
        return default_prompt
# ===== end BRICK 5 backend =====
''', 1),
]


def fail(msg):
    print("ABORTED: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def main():
    check_only = "--check" in sys.argv
    try:
        own = open(__file__, encoding="utf-8").read()
    except Exception:
        own = ""
    if LT in own or GT in own or AMP in own:
        fail("this script was altered in transit (raw angle bracket or ampersand found). Download it again.")
    try:
        text = open(TARGET, encoding="utf-8").read()
    except Exception as e:
        fail("cannot read " + TARGET + ": " + str(e))
    if MARKER in text:
        fail("Brick 5 is already applied to " + TARGET + ".")
    for label, needle in PREREQS:
        if needle not in text:
            fail(label + " is not applied to " + TARGET + ". Apply it first.")
    new = text
    for name, old, rep, count in EDITS:
        old, rep = dec(old), dec(rep)
        found = new.count(old)
        if found != count:
            fail("anchor '" + name + "' found " + str(found) + " time(s), expected " + str(count) + ".")
        new = new.replace(old, rep)
    if MARKER not in new:
        fail("marker missing after patching.")
    try:
        compile(new, TARGET, "exec")
    except SyntaxError as e:
        fail("patched main.py does not compile: " + str(e))
    if check_only:
        print("CHECK OK: all prerequisites and " + str(len(EDITS)) + " anchors found. Run without --check to apply.")
        return
    shutil.copyfile(TARGET, BACKUP)
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new)
    print("PATCHED " + TARGET + " (" + str(len(text)) + " -" + chr(62) + " " + str(len(new)) + " bytes). Backup: " + BACKUP)


if __name__ == "__main__":
    main()
