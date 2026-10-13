#!/usr/bin/env python3
"""
patch_brickF3.py - Brick F.3: kill the remaining framework-name leaks (main.py only)

What it does (10 anchors, each expected once in the original file)
  F3-1   _E3_JARGON_CAPS gets ECAFI.
  F3-2   _E3_JARGON_NAMES gets 25 names (Big Idea and Editorial Calendar left out on purpose),
         then _f3_banned_words / _f3_plain_rule, and SELF_CRITIQUE_BLOCK is filled in.
  F3-3   SELF_CRITIQUE_BLOCK rule 1 becomes the plain-words rule (placeholder [F3_PLAIN_RULE]).
  F3-4   /api/chat notes label becomes COACH NOTES (use the ideas, never the names; ...).
  F3-5   /api/chat empty notes text becomes "No notes matched."
  F3-6   /api/chat "Apply frameworks." becomes the plain-words line.
  F3-7   /api/chat rule 1 becomes {_f3_plain_rule()} (built on every request).
  F3-8   /api/chat/stream notes label becomes COACH NOTES (use the ideas, never the names).
  F3-9   /api/chat/stream "Apply frameworks." becomes the plain-words line.
  F3-10  /api/analyze-funnel "Cite frameworks (...)" becomes the plain-words line.
  Not touched: _b5_system_prompt (already clean), agentic_core.py (Brick F.3b),
  chat_test.html jargon lists (Brick F.3c).

Safety
  - Needs BRICK F.2 in main.py. Refuses a second run (BRICK F.3 in main.py).
  - Every anchor is counted on the original file before anything is written.
  - Checks the lists, the filled self-critique block, the /api/chat prompt, the grader
    jargon check, and py_compile.
  - Backup main.py.bak-brickF3 (never overwritten). Atomic write. CRLF safe.

Usage
  python3 patch_brickF3.py --dry-run
  python3 patch_brickF3.py
  python3 patch_brickF3.py --dir /root/e5-ai-coach

Rollback
  cp main.py.bak-brickF3 main.py   then restart FastAPI
"""
import argparse
import ast
import os
import py_compile
import re
import shutil
import sys
import tempfile

MARKER = "BRICK F.3"
PREREQ = "BRICK F.2"
TOKENS = ("@LT@", "@GT@", "@AMP@", "@MDASH@")
DROPPED = ("Big Idea", "Editorial Calendar")

MAIN_ANCHORS = [
    (
        'F3-1 add ECAFI to CAPS',
        '_E3_JARGON_CAPS = ["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S"]',
        '_E3_JARGON_CAPS = ["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S", "ECAFI"]',
        1,
    ),
    (
        'F3-2 add 25 names + plain rule',
        '                    "Launch Planner", "21-day launch map", "Customer Value Journey"]\n',
        '                    "Launch Planner", "21-day launch map", "Customer Value Journey",\n                    # BRICK F.3: 25 more names from the framework corpus (Big Idea and Editorial Calendar left out on purpose)\n                    "Jim Hamilton", "Todd Brown", "Kevin Rogers", "Chris Rocheleau",\n                    "Bart Schutz", "DigitalMarketer", "Alex Cattoni", "Bullet Campaign",\n                    "Message Mapping", "Copywriting Crossroads", "Email Storyselling", "Write and Ignite",\n                    "Predictable Sales System", "Predictable Sales Canvas", "Ready Now Funnel", "Flood Your Funnel",\n                    "Self Liquidating Offer", "Trial Upgrade Offer", "Value Journey", "Before After Grid",\n                    "Gain Logic Fear", "Indoctrination Series", "Social Media Scorecards", "Lead Magnet Builder",\n                    "Qualified Email"]\n\n# ===== BRICK F.3: one plain-words rule for every coach prompt (same lists as the grader) =====\ndef _f3_banned_words():\n    return ", ".join(_E3_JARGON_CAPS + _E3_JARGON_NAMES)\n\n\ndef _f3_plain_rule():\n    return ("Plain everyday words only. Never name a framework, method, book or author. "\n            "Never write any of these words: " + _f3_banned_words() + ".")\n\n\nSELF_CRITIQUE_BLOCK = SELF_CRITIQUE_BLOCK.replace("[F3_PLAIN_RULE]", _f3_plain_rule())\n# ===== end BRICK F.3 =====\n',
        1,
    ),
    (
        'F3-3 SELF_CRITIQUE_BLOCK rule 1',
        'SELF_CRITIQUE_BLOCK = """\n\nSELF-CRITIQUE (run this checklist on your draft BEFORE you output it. Do not output the checklist itself):\n1. Framework cited by name? (e.g., Hormozi Value Equation, AVOCADO, CVJ). If no, add one from the FRAMEWORK EXCERPTS above.\n',
        'SELF_CRITIQUE_BLOCK = """\n\nSELF-CRITIQUE (run this checklist on your draft BEFORE you output it. Do not output the checklist itself):\n1. [F3_PLAIN_RULE]\n',
        1,
    ),
    (
        'F3-4 /api/chat notes label',
        "RELEVANT FRAMEWORK EXCERPTS (retrieved from your 403 knowledge files @MDASH@ use ONLY if directly relevant to the user's question, otherwise ignore):",
        "COACH NOTES (use the ideas, never the names; use ONLY if directly relevant to the user's question, otherwise ignore):",
        1,
    ),
    (
        'F3-5 /api/chat empty notes text',
        '"No specific framework matched this query."',
        '"No notes matched."',
        1,
    ),
    (
        'F3-6 /api/chat Apply frameworks',
        "reference the user's actual work. Apply frameworks. ALWAYS",
        "reference the user's actual work. Use plain everyday words, never framework names. ALWAYS",
        1,
    ),
    (
        'F3-7 /api/chat rule 1',
        'No walls of text.\n\nSELF-CRITIQUE (run this checklist on your draft BEFORE you output it. Do not output the checklist itself):\n1. Framework cited by name? (e.g., Hormozi Value Equation, AVOCADO, CVJ). If no, add one from the FRAMEWORK EXCERPTS above.\n',
        'No walls of text.\n\nSELF-CRITIQUE (run this checklist on your draft BEFORE you output it. Do not output the checklist itself):\n1. {_f3_plain_rule()}\n',
        1,
    ),
    (
        'F3-8 /api/chat/stream notes label',
        '        "FRAMEWORK EXCERPTS:" + N + (framework_context if framework_context else "None matched.") + N + N +\n',
        '        "COACH NOTES (use the ideas, never the names):" + N + (framework_context if framework_context else "None matched.") + N + N +\n',
        1,
    ),
    (
        'F3-9 /api/chat/stream Apply frameworks',
        'Personalize. Apply frameworks. ALWAYS',
        'Personalize. Use plain everyday words, never framework names. ALWAYS',
        1,
    ),
    (
        'F3-10 /api/analyze-funnel cite rule',
        'Cite frameworks (CVJ, STORM, Value Equation).',
        'Use plain everyday words, never framework names.',
        1,
    ),
]


def decode(s):
    return (s.replace("@LT@", chr(60)).replace("@GT@", chr(62))
            .replace("@AMP@", chr(38)).replace("@MDASH@", chr(0x2014)))


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
        print("  %-38s found %d (expected %d)" % (name, n, expected))
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


def block(out, start_marker, end_marker):
    s = out.index(start_marker)
    e = out.index(end_marker, s) + len(end_marker)
    return out[s:e]


def check_lists_and_rule(out):
    sc = block(out, 'SELF_CRITIQUE_BLOCK = """', 'Only output the FINAL improved version."""')
    lists = block(out, "_E3_JARGON_CAPS = [", "# ===== end BRICK F.3 =====")
    ns = {}
    exec(sc + "\n" + lists, ns)
    caps, names = ns["_E3_JARGON_CAPS"], ns["_E3_JARGON_NAMES"]
    if len(caps) != 9 or "ECAFI" not in caps:
        fail("CAPS list should have 9 words incl. ECAFI, has " + str(len(caps)))
    if len(names) != 45:
        fail("NAMES list should have 45 names, has " + str(len(names)))
    low = [w.lower() for w in caps + names]
    if len(set(low)) != len(low):
        fail("duplicate jargon word")
    for d in DROPPED:
        if d.lower() in low:
            fail(d + " must not be in the list")
    for w in ("Cattoni", "Alex Cattoni", "Value Journey", "Qualified Email", "DigitalMarketer"):
        if w not in names:
            fail(w + " missing from NAMES")
    block_txt = ns["SELF_CRITIQUE_BLOCK"]
    if "[F3_PLAIN_RULE]" in block_txt or "1. Plain everyday words only." not in block_txt or "ECAFI" not in block_txt:
        fail("SELF_CRITIQUE_BLOCK was not filled in")
    for w in ("Framework cited", "FRAMEWORK EXCERPTS"):
        if w in block_txt:
            fail("SELF_CRITIQUE_BLOCK still has: " + w)
    print("  lists: 9 caps + 45 names = 54, no duplicates, Big Idea and Editorial Calendar left out")
    print("  SELF_CRITIQUE_BLOCK rule 1 filled with the plain-words rule")
    return ns


def check_chat_prompt(out, ns):
    src = block(out, 'system_prompt = f"""You are the E5 AI Coach.', 'Only output the FINAL improved version."""')
    expr = src[len("system_prompt = "):]
    env = {"profile": {}, "journey": {}, "phase_info": {"name": "Foundation"}, "current_task": {"name": "Define your offer"},
           "traffic_source": "content", "task_status_line": "open", "standups_text": "None", "wins_full_text": "None",
           "scores_text": "None", "framework_context": "", "_f3_plain_rule": ns["_f3_plain_rule"]}
    try:
        p = eval(expr, env)
    except Exception as e:
        fail("/api/chat prompt does not evaluate: " + str(e))
    for w in ("COACH NOTES (use the ideas, never the names;", "No notes matched.", "1. Plain everyday words only.",
              "Never write any of these words: STORM", "never framework names. ALWAYS"):
        if w not in p:
            fail("/api/chat prompt missing: " + w)
    for w in ("FRAMEWORK EXCERPTS", "Apply frameworks", "Framework cited"):
        if w in p:
            fail("/api/chat prompt still has: " + w)
    print("  /api/chat prompt: COACH NOTES label, plain-words rules, banned list filled on each request")


def check_grader(out, ns):
    src = block(out, "def _e3_has_jargon(s):", "return bool(re.search(caps, s) or re.search(names, s))")
    g = {"re": re, "_E3_JARGON_CAPS": ns["_E3_JARGON_CAPS"], "_E3_JARGON_NAMES": ns["_E3_JARGON_NAMES"]}
    exec(src, g)
    f = g["_e3_has_jargon"]
    cases = [("Use the ECAFI steps", True), ("Try the digitalmarketer way", True), ("Map your value journey", True),
             ("Plan your editorial calendar", False), ("Your big idea is strong", False), ("a storm of posts", False),
             ("Read Alex Cattoni", True)]
    for s, want in cases:
        if bool(f(s)) != want:
            fail("grader jargon check wrong on: " + s)
    print("  grader jargon check: new words caught, everyday phrases and lowercase storm kept")


def main():
    ap = argparse.ArgumentParser(description="Brick F.3: remove remaining framework-name leaks")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = os.path.join(args.dir, "main.py")
    if not os.path.isfile(path):
        fail("main.py not found in " + os.path.abspath(args.dir))
    raw = open(path, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if MARKER in text:
        fail("Brick F.3 is already applied to main.py (second run refused)")
    if PREREQ not in text:
        fail("BRICK F.2 not found in main.py. Apply Brick F.2 first.")
    print("main.py: " + path + (" (CRLF)" if crlf else ""))
    print("Anchors:")
    out = apply_anchors(text)
    print("Checks:")
    if MARKER not in out:
        fail("marker missing after patch")
    for t in TOKENS:
        if t in out:
            fail("token " + t + " left in output")
    added = set(out) - set(text)
    if [c for c in added if not c.isascii()]:
        fail("non-ASCII text added")
    for w in ("Framework cited by name", "Apply frameworks", "FRAMEWORK EXCERPTS", "Cite frameworks", "No specific framework matched"):
        if w in out:
            fail("old text still present: " + w)
    if out.count("{_f3_plain_rule()}") != 1 or out.count("[F3_PLAIN_RULE]") != 2:
        fail("plain-rule hooks count is wrong")
    print("  old framework instructions gone from main.py")
    ns = check_lists_and_rule(out)
    check_chat_prompt(out, ns)
    check_grader(out, ns)
    final = out.replace("\n", "\r\n") if crlf else out
    fd, tmp = tempfile.mkstemp(prefix=".brickF3-", suffix=".py", dir=os.path.dirname(os.path.abspath(path)))
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
        bak = path + ".bak-brickF3"
        if os.path.exists(bak):
            print("Backup already exists, kept as is: " + bak)
        else:
            shutil.copy2(path, bak)
            print("Backup: " + bak)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
        tmp = None
        print("DONE: Brick F.3 applied. Restart FastAPI.")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
