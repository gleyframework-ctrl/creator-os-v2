#!/usr/bin/env python3
"""
patch_brickF2.py - Brick F.2: no framework names in AI-generated tasks (main.py only)

What it does (7 anchors, each expected once)
  F2-1  Adds _f2_clean_tasks before /api/generate-tasks: keeps name, why, deliverable,
        deliverables, deadline_days only; frameworks is always []; a task with a jargon
        word (_E3_JARGON_CAPS case-sensitive, _E3_JARGON_NAMES case-insensitive,
        whole words) is dropped.
  F2-2  Excerpts label becomes COACH NOTES (use the ideas, never the names).
  F2-3  The output format no longer asks for a framework field.
  F2-4  The framework rule becomes a plain-words rule with the banned words built at
        runtime from _E3_JARGON_CAPS + _E3_JARGON_NAMES (same source as the grader).
  F2-5  No-tasks error: raw removed from the reply, logged on the server.
  F2-6  Success reply goes through _f2_clean_tasks. All dropped for jargon gives
        "Those tasks used coach jargon. Please try again." Junk gives "No tasks in response".
  F2-7  Parse error: raw removed from the reply, logged on the server.

Safety
  - Needs BRICK G in main.py. Refuses a second run (BRICK F.2 in main.py).
  - Every anchor is counted before anything is written.
  - Offline test of _f2_clean_tasks and of the prompt rule line, then py_compile.
  - Backup main.py.bak-brickF2 (never overwritten). Atomic write. CRLF safe.

Usage
  python3 patch_brickF2.py --dry-run
  python3 patch_brickF2.py
  python3 patch_brickF2.py --dir /root/e5-ai-coach

Rollback
  cp main.py.bak-brickF2 main.py   then restart FastAPI
"""
import argparse
import ast
import os
import py_compile
import re
import shutil
import sys
import tempfile

MARKER = "BRICK F.2"
PREREQ = "BRICK G"
TOKENS = ("@LT@", "@GT@", "@AMP@", "@MDASH@")

MAIN_ANCHORS = [
    (
        'F2-1 task cleaner before the route',
        '@app.post("/api/generate-tasks")\n',
        '# ===== BRICK F.2: no framework names in AI-generated tasks =====\n# Only these fields are kept. frameworks is always [] so the frontend never falls back to [t.framework].\n# A task whose text holds a jargon word is dropped (never scrubbed). Same lists as the grader.\n_F2_ALLOWED = ("name", "why", "deliverable", "deliverables", "deadline_days")\n\n\ndef _f2_has_jargon(text):\n    text = str(text or "")\n    for w in _E3_JARGON_CAPS:\n        if re.search(r"(?@LT@![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text):\n            return True\n    for w in _E3_JARGON_NAMES:\n        if re.search(r"(?@LT@![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text, re.I):\n            return True\n    return False\n\n\ndef _f2_clean_tasks(tasks):\n    cleaned, dropped_for_jargon = [], 0\n    for t in (tasks if isinstance(tasks, list) else []):\n        if not isinstance(t, dict):\n            continue\n        c = {}\n        for k in _F2_ALLOWED:\n            if k not in t:\n                continue\n            v = t[k]\n            if k == "deliverables":\n                if isinstance(v, list):\n                    c[k] = [str(x) for x in v if isinstance(x, (str, int, float))]\n            elif k == "deadline_days":\n                if isinstance(v, (int, float, str)):\n                    c[k] = v\n            elif isinstance(v, (str, int, float)):\n                c[k] = str(v)\n        if not str(c.get("name", "")).strip():\n            continue\n        texts = [c.get("name", ""), c.get("why", ""), c.get("deliverable", "")] + c.get("deliverables", [])\n        if any(_f2_has_jargon(x) for x in texts):\n            dropped_for_jargon += 1\n            continue\n        c["frameworks"] = []\n        cleaned.append(c)\n    return cleaned, dropped_for_jargon\n# ===== end BRICK F.2 =====\n\n\n@app.post("/api/generate-tasks")\n',
        1,
    ),
    (
        'F2-2 relabel excerpts',
        '        + "FRAMEWORK EXCERPTS:" + N + (framework_context if framework_context else "None.") + N + N\n',
        '        + "COACH NOTES (use the ideas, never the names):" + N + (framework_context if framework_context else "None.") + N + N\n',
        1,
    ),
    (
        'F2-3 drop framework field in output',
        '"why": "one sentence why this task matters for THIS user", "framework": "real framework name", "deliverable":',
        '"why": "one sentence why this task matters for THIS user", "deliverable":',
        1,
    ),
    (
        'F2-4 plain-words rule',
        'Only cite frameworks that relate to offers, funnels, content, traffic, or conversion @MDASH@ NEVER Human Design, spiritual, or personality frameworks unless the user asked. If the FRAMEWORK EXCERPTS above do not relate to the bottleneck, IGNORE them and use Hormozi, AVOCADO, or DigitalMarketer frameworks instead. ',
        'Use plain everyday words. Never name a framework, method, book or author. Never write any of these words: " + ", ".join(_E3_JARGON_CAPS + _E3_JARGON_NAMES) + ". Use the ideas in COACH NOTES, never their names. If the notes do not relate to the bottleneck, ignore them. ',
        1,
    ),
    (
        'F2-5 no-tasks error without raw',
        '            return {"ok": False, "error": "No tasks in response", "raw": raw[:500]}\n',
        '            log.warning("BRICK F.2: generate-tasks returned no tasks. raw=" + raw[:500])\n            return {"ok": False, "error": "No tasks in response"}\n',
        1,
    ),
    (
        'F2-6 success goes through cleaner',
        '        return {"ok": True, "tasks": tasks, "generated_for_day": journey.get(\'current_day\',1), "phase": phase_info[\'name\']}\n',
        '        tasks, dropped = _f2_clean_tasks(tasks)\n        if not tasks:\n            log.warning("BRICK F.2: all generated tasks dropped (jargon=" + str(dropped) + ")")\n            return {"ok": False, "error": "Those tasks used coach jargon. Please try again." if dropped else "No tasks in response"}\n        return {"ok": True, "tasks": tasks, "generated_for_day": journey.get(\'current_day\',1), "phase": phase_info[\'name\']}\n',
        1,
    ),
    (
        'F2-7 parse error without raw',
        '        return {"ok": False, "error": "Parse failed: " + str(e), "raw": raw[:500]}\n',
        '        log.warning("BRICK F.2: generate-tasks parse failed: " + str(e) + " raw=" + raw[:500])\n        return {"ok": False, "error": "Parse failed: " + str(e)}\n',
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


def list_literal(text, name):
    m = re.search(r"^" + name + r" = (\[.*?\])\s*$", text, re.M | re.S)
    if not m:
        fail("could not read " + name + " from main.py")
    return ast.literal_eval(m.group(1))


def apply_anchors(text):
    out = text
    for name, old, new, expected in MAIN_ANCHORS:
        old, new = decode(old), decode(new)
        n = out.count(old)
        print("  %-36s found %d (expected %d)" % (name, n, expected))
        if n != expected:
            fail("anchor '" + name + "' count is " + str(n) + ", expected " + str(expected))
        out = out.replace(old, new)
    return out


def check_cleaner(out):
    start = out.index("# ===== BRICK F.2: no framework names")
    end = out.index("# ===== end BRICK F.2 =====")
    ns = {"re": re,
          "_E3_JARGON_CAPS": list_literal(out, "_E3_JARGON_CAPS"),
          "_E3_JARGON_NAMES": list_literal(out, "_E3_JARGON_NAMES")}
    exec(out[start:end], ns)
    clean = ns["_f2_clean_tasks"]
    good = {"name": "Post one storm of short videos", "why": "Short posts bring new people.",
            "framework": "Value Equation (Hormozi)", "frameworks": ["AVOCADO"], "deliverable": "3 posts",
            "deadline_days": 7, "extra": "x", "id": "abc"}
    bad = {"name": "Price your offer", "why": "Use the Value Equation (Hormozi) to set it.", "deliverable": "A price"}
    bad2 = {"name": "Write a STORM email", "why": "x", "deliverables": ["one email"]}
    tasks, dropped = clean([good, bad, "junk", 5, None, {"why": "no name"}, bad2])
    if dropped != 2 or len(tasks) != 1:
        fail("cleaner test: expected 1 kept and 2 dropped, got " + str(len(tasks)) + " and " + str(dropped))
    t = tasks[0]
    if sorted(t.keys()) != ["deadline_days", "deliverable", "frameworks", "name", "why"]:
        fail("cleaner test: wrong keys " + str(sorted(t.keys())))
    if t["frameworks"] != [] or t["name"] != good["name"]:
        fail("cleaner test: frameworks not [] or lowercase storm was dropped")
    if clean([bad, bad2]) != ([], 2):
        fail("cleaner test: all-jargon case wrong")
    if clean(["junk", {"x": 1}]) != ([], 0) or clean("not a list") != ([], 0):
        fail("cleaner test: junk case wrong")
    print("  cleaner: extra keys dropped, frameworks [], jargon task dropped, lowercase storm kept, junk skipped, counts right")
    return ns


def check_prompt(out, ns):
    line = [l for l in out.split("\n") if "Use plain everyday words." in l]
    if len(line) != 1:
        fail("plain-words rule line not found once")
    src = line[0].strip()
    if src.startswith("+"):
        src = src[1:]
    env = {"N": "\n", "bottleneck": "traffic",
           "_E3_JARGON_CAPS": ns["_E3_JARGON_CAPS"], "_E3_JARGON_NAMES": ns["_E3_JARGON_NAMES"]}
    try:
        rule = eval(src, env)
    except Exception as e:
        fail("rule line does not evaluate: " + str(e))
    for w in ("Hormozi", "AVOCADO", "Customer Value Journey", "Deadline 3-14 days. Never generic.", "(traffic)"):
        if w not in rule:
            fail("rule line missing: " + w)
    print("  prompt: banned-word list filled at runtime, bottleneck and deadline rules kept")


def main():
    ap = argparse.ArgumentParser(description="Brick F.2: no framework names in generated tasks")
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
        fail("Brick F.2 is already applied to main.py (second run refused)")
    if PREREQ not in text:
        fail("BRICK G not found in main.py. Apply Brick G first.")
    print("main.py: " + path + (" (CRLF)" if crlf else ""))
    print("Anchors:")
    out = apply_anchors(text)
    print("Checks:")
    if MARKER not in out:
        fail("marker missing after patch")
    for t in TOKENS:
        if t in out:
            fail("token " + t + " left in output")
    if text.isascii() and not out.isascii():
        fail("non-ASCII text added")
    if out.count("raw[:500]") != 2 or out.count('"raw": raw') != 0:
        fail("raw still in a reply")
    if [l for l in out.split("\n") if "raw[:500]" in l and "log.warning(" not in l]:
        fail("raw[:500] used outside log.warning")
    for gone in ("real framework name", "use Hormozi, AVOCADO", 'FRAMEWORK EXCERPTS:" + N + (framework_context if framework_context else "None.")'):
        if gone in out:
            fail("old text still present: " + gone)
    print("  raw only in server logs, old framework prompt text gone")
    ns = check_cleaner(out)
    check_prompt(out, ns)
    final = out.replace("\n", "\r\n") if crlf else out
    fd, tmp = tempfile.mkstemp(prefix=".brickF2-", suffix=".py", dir=os.path.dirname(os.path.abspath(path)))
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
        bak = path + ".bak-brickF2"
        if os.path.exists(bak):
            print("Backup already exists, kept as is: " + bak)
        else:
            shutil.copy2(path, bak)
            print("Backup: " + bak)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
        tmp = None
        print("DONE: Brick F.2 applied. Restart FastAPI.")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
