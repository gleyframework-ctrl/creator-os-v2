#!/usr/bin/env python3
"""
patch_brickG.py - Brick G: realign the task list (main.py only)

What it does
  G1  Renames the old 3-phase map to JOURNEY_MAP_V1 (kept for reference, not used).
  G2  Adds the new 5-phase JOURNEY_MAP: 18 tasks, one every 5 days, frameworks [] on every task.
  G3  Makes advance_journey generic (next phase only when every task of the phase is done).
  G4  Day counter moves +5 per task instead of +7.
  G5  total_tasks is counted from the map (18) instead of the hardcoded 12.
  G6  One-time reset of journeys that still hold the 10 retired task ids
      (p1_t3, p1_t4, p2_t1..p2_t4, p3_t1..p3_t4). xp, streak, badges and
      last_standup_date are kept. Old completed ids move to tasks_completed_legacy.

Safety
  - Needs Brick F.1 in main.py. Refuses to run twice.
  - Every anchor is counted before anything is written.
  - Checks the new map, jargon, a full 18-task walk, the reset logic, and py_compile.
  - Backup main.py.bak-brickG (never overwritten). Atomic write.

Usage
  python3 patch_brickG.py --dry-run      check only, write nothing
  python3 patch_brickG.py                apply in the current folder
  python3 patch_brickG.py --dir /root/e5-ai-coach

Rollback
  cp main.py.bak-brickG main.py   then restart FastAPI
"""
import argparse
import ast
import os
import py_compile
import re
import shutil
import sys
import tempfile

MARKER = "# BRICK G:"
PREREQ = "BRICK F.1"
RETIRED = ("p1_t3", "p1_t4", "p2_t1", "p2_t2", "p2_t3", "p2_t4", "p3_t1", "p3_t2", "p3_t3", "p3_t4")

MAIN_ANCHORS = [
    (
        'G1 fold away the old map',
        'JOURNEY_MAP = {\n',
        'JOURNEY_MAP_V1 = {  # BRICK G: old 3-phase map, kept for reference, not used\n',
        1,
    ),
    (
        'G2 insert the new 5-phase map',
        r'''# ============================================================
# DATABASE HELPERS
''',
        r'''# ===== BRICK G: 5-phase journey (Foundation, Product, Community, Traffic, Retention). 18 tasks, one every 5 days. =====
# Scale (Phase 6) comes in a later brick. No framework names: frameworks is [] on every task (key kept).
# Each task sets standup_link / standup_metrics, which _e3_rubric already reads. The grader is not changed.
JOURNEY_MAP = {
    "Phase 1": {
        "name": "Foundation", "days": "1-15", "focus": "Who you help and what you sell", "sub_coach": "Foundation Coach",
        "tasks": [
            {"id": "p1_t1", "name": "Define your offer", "deadline_day": 1, "why": "A clear offer makes every next step easier.",
             "frameworks": [], "deliverables": ["Your offer in one sentence", "3 results your customer gets", "Your price and your guarantee"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p1_t2", "name": "Know your customer", "deadline_day": 6, "why": "When you know one person well, your words reach them.",
             "frameworks": [], "deliverables": ["Who they are and their situation", "Their 3 biggest worries", "Their 3 biggest wishes", "Where they spend time online"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p1_position", "name": "Write your positioning statement", "deadline_day": 11, "why": "One clear sentence tells people why you are the right choice.",
             "frameworks": [], "deliverables": ["One sentence: I help [who] get [result] without [pain]", "Why they should pick you over other options"],
             "standup_link": False, "standup_metrics": False},
        ]
    },
    "Phase 2": {
        "name": "Product", "days": "16-30", "focus": "Prove people want it before you build it", "sub_coach": "Product Coach",
        "tasks": [
            {"id": "p2_presell", "name": "Build a one-page pre-sell", "deadline_day": 16, "why": "A simple page lets people say yes before you build the full product.",
             "frameworks": [], "deliverables": ["A headline with the main result", "Who it is for", "Your 3 results", "Your price and how to say yes"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p2_walkthrough", "name": "Record a 5-minute offer walkthrough", "deadline_day": 21, "why": "A short video explains your offer better than a long text.",
             "frameworks": [], "deliverables": ["A video of 5 minutes or less about your offer", "Link to the video"],
             "standup_link": True, "standup_metrics": False},
            {"id": "p2_signals", "name": "Get 3 people to say \"I'd buy this\"", "deadline_day": 26, "why": "Real people saying yes proves your offer before you build it.",
             "frameworks": [], "deliverables": ["How many people you talked to", "3 people who said they would buy", "What they said, in their words"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
    "Phase 3": {
        "name": "Community", "days": "31-50", "focus": "A home for your paying members", "sub_coach": "Community Coach",
        "tasks": [
            {"id": "p3_create", "name": "Create your community on Whop or Skool", "deadline_day": 31, "why": "Your community is your shop, your classroom and your checkout in one place.",
             "frameworks": [], "deliverables": ["Community created", "Link to your community"],
             "standup_link": True, "standup_metrics": False},
            {"id": "p3_welcome", "name": "Write your welcome post", "deadline_day": 36, "why": "A good welcome helps new members feel at home and take a first step.",
             "frameworks": [], "deliverables": ["Who the community is for", "What members get", "The first step to take"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p3_channels", "name": "Set up your channels", "deadline_day": 41, "why": "Clear channels help members find what they need.",
             "frameworks": [], "deliverables": ["3 to 5 channels with clear names", "One line on what goes in each"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p3_pricing", "name": "Set your pricing tiers", "deadline_day": 46, "why": "Clear prices make it easy to say yes.",
             "frameworks": [], "deliverables": ["1 to 3 price levels", "What each level includes", "The price of each level"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
    "Phase 4": {
        "name": "Traffic", "days": "51-70", "focus": "Bring the right people to your community", "sub_coach": "Traffic Coach",
        "tasks": [
            {"id": "p4_diagnostic", "name": "Answer the 12-question traffic check", "deadline_day": 51, "why": "Your answers show which way of finding people fits you best.",
             "frameworks": [], "deliverables": ["Your audience, past clients and warm contacts", "Your time and budget", "What you are comfortable doing: camera, writing, messages, live calls", "Your offer status and price"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p4_method", "name": "Pick one traffic method", "deadline_day": 56, "why": "One method done well beats five done halfway. No audience yet? Sending 100 messages a day works.",
             "frameworks": [], "deliverables": ["The 3 methods the coach suggested", "The one you picked and why", "Your plan for the first week"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p4_launch", "name": "Launch your method and log your first link", "deadline_day": 61, "why": "Starting is the hardest part. Your first link proves you started.",
             "frameworks": [], "deliverables": ["What you launched", "Link to your first post, message or page"],
             "standup_link": True, "standup_metrics": False},
            {"id": "p4_first_sale", "name": "Record your first sale", "deadline_day": 66, "why": "Your first sale proves people will pay for what you offer.",
             "frameworks": [], "deliverables": ["Who bought", "What they paid", "How they found you"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
    "Phase 5": {
        "name": "Retention", "days": "71-90", "focus": "Keep members happy and growing", "sub_coach": "Retention Coach",
        "tasks": [
            {"id": "p5_engagement", "name": "Plan your weekly member activity", "deadline_day": 71, "why": "A steady weekly rhythm keeps members coming back.",
             "frameworks": [], "deliverables": ["One thing you post or host every week", "The day and time"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p5_audit", "name": "Check why members stay or leave", "deadline_day": 76, "why": "Knowing why people stay or leave shows you what to fix.",
             "frameworks": [], "deliverables": ["How many members joined", "How many members left", "2 reasons people stay or leave"],
             "standup_link": False, "standup_metrics": True},
            {"id": "p5_upsell", "name": "Write your next offer for members", "deadline_day": 81, "why": "Happy members often want more help from you.",
             "frameworks": [], "deliverables": ["The next offer for current members", "Its price", "How you will tell members"],
             "standup_link": False, "standup_metrics": True},
            {"id": "p5_workshop", "name": "Run a 6-day workshop", "deadline_day": 86, "why": "A short live workshop brings members together and brings new people in.",
             "frameworks": [], "deliverables": ["The 6 topics", "How many people joined", "What you learned"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
}
# ===== end BRICK G map =====

# ============================================================
# DATABASE HELPERS
''',
        1,
    ),
    (
        'G3 generalize advance_journey',
        r'''def advance_journey(journey, member_id):
    phase = journey["current_phase"]
    phase_tasks = JOURNEY_MAP[phase]["tasks"]
    completed = journey.get("tasks_completed", [])
    completed_in_phase = [t for t in phase_tasks if t["id"] in completed]
    if phase == "Phase 1" and len(completed_in_phase) @GT@= 4:
        journey["current_phase"] = "Phase 2"; journey["current_task_id"] = "p2_t1"
    elif phase == "Phase 2" and len(completed_in_phase) @GT@= 4:
        journey["current_phase"] = "Phase 3"; journey["current_task_id"] = "p3_t1"
    else:
        remaining = [t for t in phase_tasks if t["id"] not in completed]
        if remaining: journey["current_task_id"] = remaining[0]["id"]

''',
        r'''def advance_journey(journey, member_id):
    # BRICK G: generic. Move to the next phase only when every task in the current phase is done.
    # No phase names or task ids are hardcoded. After the last phase, nothing changes (same as before).
    keys = list(JOURNEY_MAP.keys())
    phase = journey.get("current_phase")
    if phase not in JOURNEY_MAP:
        phase = keys[0]
        journey["current_phase"] = phase
    completed = journey.get("tasks_completed", []) or []
    remaining = [t for t in JOURNEY_MAP[phase]["tasks"] if t["id"] not in completed]
    if remaining:
        journey["current_task_id"] = remaining[0]["id"]
        return
    i = keys.index(phase)
    if i + 1 != len(keys):
        nxt = keys[i + 1]
        journey["current_phase"] = nxt
        nxt_remaining = [t for t in JOURNEY_MAP[nxt]["tasks"] if t["id"] not in completed]
        journey["current_task_id"] = (nxt_remaining or JOURNEY_MAP[nxt]["tasks"])[0]["id"]

''',
        1,
    ),
    (
        'G4 day counter +7 to +5',
        '        journey["current_day"] = min(90, journey.get("current_day",1) + 7)\n',
        '        journey["current_day"] = min(90, journey.get("current_day",1) + 5)  # BRICK G: 18 tasks x 5 days\n',
        1,
    ),
    (
        'G5 task total from the map',
        '        total_tasks = 12\n',
        '        total_tasks = sum(len(v["tasks"]) for v in JOURNEY_MAP.values())  # BRICK G\n',
        1,
    ),
    (
        'G6 one-time reset wrapper',
        'install_strict_database(globals())\n',
        r'''install_strict_database(globals())

# ===== BRICK G: one-time reset of test journeys that still use the old 3-phase task ids =====
# Runs only for a journey whose current task or completed list holds one of these 10 retired ids.
# The list is hardcoded on purpose (never pattern-based), so a journey is reset at most once,
# and future map changes can never trigger it. The reset is WRITTEN first and then returned,
# so the standup snapshot always matches the saved row (no 409). A failed write raises 503.
_G_RETIRED_IDS = ("p1_t3", "p1_t4", "p2_t1", "p2_t2", "p2_t3", "p2_t4", "p3_t1", "p3_t2", "p3_t3", "p3_t4")
_g_db_get_journey_strict = db_get_journey


def _g_needs_reset(journey):
    if not isinstance(journey, dict):
        return False
    if str(journey.get("current_task_id") or "") in _G_RETIRED_IDS:
        return True
    return any(str(t) in _G_RETIRED_IDS for t in (journey.get("tasks_completed") or []))


def _g_reset(journey):
    j = dict(journey)
    legacy = list(j.get("tasks_completed_legacy") or [])
    for t in (journey.get("tasks_completed") or []):
        if t not in legacy:
            legacy.append(t)
    j.update({"current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [],
              "current_day": 1, "tasks_completed_legacy": legacy,
              "brick_g_reset_at": datetime.now().isoformat()})
    return j


def db_get_journey(member_id):
    journey = _g_db_get_journey_strict(member_id)
    if _g_needs_reset(journey):
        journey = _g_reset(journey)
        db_upsert_journey(member_id, journey)
        log.info("BRICK G: journey reset to the new Phase 1 for member " + str(member_id))
    return journey
# ===== end BRICK G reset =====
''',
        1,
    ),
]


def decode(s):
    return s.replace("@LT@", chr(60)).replace("@GT@", chr(62)).replace("@AMP@", chr(38))


def fail(msg):
    print("ABORT: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def lte(a, b):
    return min(a, b) == a


def apply_anchors(text):
    hits = []
    for name, old, new, expected in MAIN_ANCHORS:
        old, new = decode(old), decode(new)
        n = text.count(old)
        print("  %-34s found %d (expected %d)" % (name, n, expected))
        if n != expected:
            fail("anchor '" + name + "' count is " + str(n) + ", expected " + str(expected))
        hits.append((text.index(old), old, new, name))
    hits.sort(key=lambda h: h[0])
    for a, b in zip(hits, hits[1:]):
        if not lte(a[0] + len(a[1]), b[0]):
            fail("anchors overlap: " + a[3] + " / " + b[3])
    out, pos = [], 0
    for start, old, new, name in hits:
        out.append(text[pos:start])
        out.append(new)
        pos = start + len(old)
    out.append(text[pos:])
    return "".join(out)


def list_literal(text, name):
    m = re.search(r"^" + name + r" = (\[.*?\])\s*$", text, re.M | re.S)
    if not m:
        fail("could not read " + name + " from main.py")
    return ast.literal_eval(m.group(1))


def check_map(out):
    start = out.index("JOURNEY_MAP = {")
    end = out.index("# ===== end BRICK G map")
    jm = ast.literal_eval(out[start + len("JOURNEY_MAP = "):end].strip())
    if list(jm.keys()) != ["Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5"]:
        fail("new map phases are wrong")
    tasks = [t for p in jm.values() for t in p["tasks"]]
    ids = [t["id"] for t in tasks]
    if len(ids) != 18 or len(set(ids)) != 18:
        fail("new map must have 18 unique task ids")
    if any(i in RETIRED for i in ids):
        fail("a retired id is still in the new map")
    for n, t in enumerate(tasks, 1):
        if t["deadline_day"] != 5 * n - 4:
            fail("deadline_day wrong on " + t["id"])
        if t.get("frameworks") != []:
            fail("frameworks must be [] on " + t["id"])
        for k in ("name", "why", "deliverables", "standup_link", "standup_metrics"):
            if k not in t:
                fail("missing key " + k + " on " + t["id"])
    for p in jm.values():
        if not p.get("sub_coach", "").endswith(" Coach"):
            fail("sub_coach must end with Coach")
    caps = list_literal(out, "_E3_JARGON_CAPS")
    names = list_literal(out, "_E3_JARGON_NAMES")
    for t in tasks:
        blob = " ".join([t["name"], t["why"]] + list(t["deliverables"]))
        for w in caps:
            if re.search(r"(?" + chr(60) + r"![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", blob):
                fail("jargon '" + w + "' in task " + t["id"])
        for w in names:
            if re.search(r"\b" + re.escape(w) + r"\b", blob, re.I):
                fail("jargon '" + w + "' in task " + t["id"])
    print("  new map: 5 phases, 18 unique ids, deadlines 1..86, frameworks [], no jargon")
    return jm


def extract_def(out, header):
    start = out.index(header)
    end = out.index("\n\n", start)
    return out[start:end] + "\n"


def check_walk(out, jm):
    ns = {"JOURNEY_MAP": jm}
    exec(extract_def(out, "def advance_journey(journey, member_id):"), ns)
    j = {"current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [], "current_day": 1}
    order = [t["id"] for p in jm.values() for t in p["tasks"]]
    seen_phases = []
    for expected in order:
        if j["current_task_id"] != expected:
            fail("walk: expected " + expected + ", got " + str(j["current_task_id"]))
        if not seen_phases or seen_phases[-1] != j["current_phase"]:
            seen_phases.append(j["current_phase"])
        j["tasks_completed"].append(expected)
        j["current_day"] = min(90, j["current_day"] + 5)
        ns["advance_journey"](j, "test")
        if not lte(j["current_day"], 90):
            fail("walk: day above 90")
    if seen_phases != list(jm.keys()):
        fail("walk: phases out of order " + str(seen_phases))
    if j["current_phase"] != "Phase 5" or j["current_task_id"] != "p5_workshop":
        fail("walk: end state changed after the last task")
    print("  walk: 18 tasks in order, Phase 1 to Phase 5, day " + str(j["current_day"]) + ", end state stable")


def check_reset(out):
    start = out.index("# ===== BRICK G: one-time reset")
    end = out.index("# ===== end BRICK G reset")
    block = out[start:end]
    store = {}
    writes = []

    class L:
        def info(self, *a):
            pass

    from datetime import datetime
    ns = {"datetime": datetime, "log": L(),
          "db_get_journey": lambda m: dict(store[m]),
          "db_upsert_journey": lambda m, d: (writes.append(m), store.__setitem__(m, dict(d)))}
    exec(block, ns)
    old = {"current_phase": "Phase 2", "current_task_id": "p2_t3", "tasks_completed": ["p1_t1", "p1_t2", "p1_t3", "p1_t4", "p2_t1"],
           "current_day": 36, "xp_total": 120, "streak": 4, "badges": ["first"], "last_standup_date": "2025-01-01"}
    store["a"] = dict(old)
    r = ns["db_get_journey"]("a")
    ok = (r["current_phase"] == "Phase 1" and r["current_task_id"] == "p1_t1" and r["tasks_completed"] == []
          and r["current_day"] == 1 and r["tasks_completed_legacy"] == old["tasks_completed"]
          and "brick_g_reset_at" in r and r["xp_total"] == 120 and r["streak"] == 4
          and r["badges"] == ["first"] and r["last_standup_date"] == "2025-01-01"
          and store["a"] == r and writes == ["a"])
    if not ok:
        fail("reset: old journey was not reset correctly")
    ns["db_get_journey"]("a")
    if writes != ["a"]:
        fail("reset: ran twice on the same journey")
    store["b"] = {"current_phase": "Phase 1", "current_task_id": "p1_position", "tasks_completed": ["p1_t1", "p1_t2"], "current_day": 11}
    ns["db_get_journey"]("b")
    if writes != ["a"]:
        fail("reset: touched a journey on the new map")
    print("  reset: old journey reset once and saved, xp/streak/badges kept, new journeys untouched")


def main():
    ap = argparse.ArgumentParser(description="Brick G: realign the task list")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = os.path.join(args.dir, "main.py")
    if not os.path.isfile(path):
        fail("main.py not found in " + os.path.abspath(args.dir))
    raw = open(path, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if "BRICK G" in text:
        fail("Brick G is already applied to main.py (second run refused)")
    if PREREQ not in text:
        fail("Brick F.1 not found in main.py. Apply Brick F.1 first.")
    if "JOURNEY_MAP_V1" in text:
        fail("JOURNEY_MAP_V1 already exists in main.py")
    print("main.py: " + path + (" (CRLF)" if crlf else ""))
    print("Anchors:")
    out = apply_anchors(text)
    print("Checks:")
    if MARKER not in out:
        fail("marker missing after patch")
    for t in ("@LT@", "@GT@", "@AMP@"):
        if t in out:
            fail("token " + t + " left in output")
    if not out.isascii() and text.isascii():
        fail("non-ASCII text added")
    if out.count("JOURNEY_MAP = {") != 1 or out.count("JOURNEY_MAP_V1 = {") != 1:
        fail("map definitions count is wrong")
    jm = check_map(out)
    check_walk(out, jm)
    check_reset(out)
    final = out.replace("\n", "\r\n") if crlf else out
    fd, tmp = tempfile.mkstemp(prefix=".brickG-", suffix=".py", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(final.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        try:
            py_compile.compile(tmp, doraise=True, cfile=tmp + "c")
        except py_compile.PyCompileError as e:
            fail("py_compile failed: " + str(e))
        finally:
            if os.path.exists(tmp + "c"):
                os.remove(tmp + "c")
        print("  py_compile OK")
        if args.dry_run:
            print("DRY RUN: all checks passed. Nothing was written.")
            return
        bak = path + ".bak-brickG"
        if os.path.exists(bak):
            print("Backup already exists, kept as is: " + bak)
        else:
            shutil.copy2(path, bak)
            print("Backup: " + bak)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
        tmp = None
        print("DONE: Brick G applied. Restart FastAPI.")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
