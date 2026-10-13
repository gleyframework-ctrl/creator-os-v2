#!/usr/bin/env python3
"""
patch_brickF3c.py - Brick F.3c: one jargon list on both sides (main.py + chat_test.html)

What it does (4 anchors, each expected once)
  C1  chat_test.html BF_JARGON_CAPS = main.py _E3_JARGON_CAPS (9 words, adds ECAFI). Marker line.
  C2  chat_test.html BF_JARGON_NAMES = main.py _E3_JARGON_NAMES (68 names: 45 + 23 new).
  C3  Arabic language rule: "Keep numbers as they are. Never name a framework, method, book or author."
  C4  main.py _E3_JARGON_NAMES gets the 23 Content drawer selector names
      (S.O.U.L.F.U.L, S.I.P.E, R.I.P.E written without the trailing dot, like F.I.B.S,
      so the whole-word check can catch them before a space).
  Everything that reads the lists updates by itself: grader, task filter, coach prompt rule,
  Try Again coach check.

Safety
  - Needs BRICK F.3 in main.py and BRICK F.2a in chat_test.html. Refuses a second run.
  - Every anchor is counted before anything is written.
  - Both lists read back from both files: identical, 9 + 68, same order, no duplicates,
    Big Idea and Editorial Calendar left out.
  - Same test phrases through the Python grader check and the JavaScript check (node):
    both must agree and give the expected result.
  - py_compile and node --check (node checks are skipped with a warning if node is missing).
  - Backups .bak-brickF3c (never overwritten). Atomic two-file write, main.py restored if
    the second write fails. CRLF safe.

Usage
  python3 patch_brickF3c.py --dry-run
  python3 patch_brickF3c.py
  python3 patch_brickF3c.py --dir /root/e5-ai-coach

Rollback
  cp main.py.bak-brickF3c main.py
  cp chat_test.html.bak-brickF3c chat_test.html
  then restart FastAPI and hard refresh the browser
"""
import argparse
import ast
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

MARKER = "BRICK F.3c"
TOKENS = ("@LT@", "@GT@", "@AMP@")
LT, GT = chr(60), chr(62)

ANCHORS = [
    (
        'html',
        'C1 frontend CAPS list',
        'const BF_JARGON_CAPS=["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S"];',
        '// BRICK F.3c: lists synced with main.py _E3_JARGON_CAPS / _E3_JARGON_NAMES (9 + 68).\nconst BF_JARGON_CAPS=["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S", "ECAFI"];',
        1,
    ),
    (
        'html',
        'C2 frontend NAMES list',
        'const BF_JARGON_NAMES=["Hormozi", "Kallaway", "Cattoni", "Tutton", "Belcher", "Rohan", "Value Equation", "Pain Stack", "Tiny Yeses", "DM Doctor", "Offer Architect", "Community OS", "Content Engine", "Dream Customer", "Dream Follower", "Hook Mastery", "Anti-viral", "Launch Planner", "21-day launch map", "Customer Value Journey"];',
        'const BF_JARGON_NAMES=["Hormozi", "Kallaway", "Cattoni", "Tutton", "Belcher", "Rohan", "Value Equation", "Pain Stack", "Tiny Yeses", "DM Doctor", "Offer Architect", "Community OS", "Content Engine", "Dream Customer", "Dream Follower", "Hook Mastery", "Anti-viral", "Launch Planner", "21-day launch map", "Customer Value Journey", "Jim Hamilton", "Todd Brown", "Kevin Rogers", "Chris Rocheleau", "Bart Schutz", "DigitalMarketer", "Alex Cattoni", "Bullet Campaign", "Message Mapping", "Copywriting Crossroads", "Email Storyselling", "Write and Ignite", "Predictable Sales System", "Predictable Sales Canvas", "Ready Now Funnel", "Flood Your Funnel", "Self Liquidating Offer", "Trial Upgrade Offer", "Value Journey", "Before After Grid", "Gain Logic Fear", "Indoctrination Series", "Social Media Scorecards", "Lead Magnet Builder", "Qualified Email", "S.O.U.L.F.U.L", "S.I.P.E", "R.I.P.E", "Content Cannon", "Objection Akido", "Value Ladder Canvas", "Perfect Offer Builder", "Million Dollar Message", "Core Message Canvas", "Green to Ripe Sequence", "MVC Build Sheets", "One Group Audit Checklist", "Ascension Map", "Growth Scorecard", "Big 3 Planning Canvas", "Insight Call Script", "Buyer Signal Cheat Sheet", "7-Scenario DM Playbook", "ICP Builder", "10 Pillars of Offer Doc", "CVJ Audit", "Step LTV Benchmark", "Bottleneck Hunter"];',
        1,
    ),
    (
        'html',
        'C3 Arabic language rule',
        "Keep numbers and framework names as they are.'",
        "Keep numbers as they are. Never name a framework, method, book or author.'",
        1,
    ),
    (
        'main',
        'C4 main.py 23 selector names',
        '                    "Qualified Email"]\n',
        '                    "Qualified Email",\n                    # BRICK F.3c: 23 Content drawer selector names (agentic_core.py FRAMEWORK_GRAPH)\n                    "S.O.U.L.F.U.L", "S.I.P.E", "R.I.P.E", "Content Cannon",\n                    "Objection Akido", "Value Ladder Canvas", "Perfect Offer Builder", "Million Dollar Message",\n                    "Core Message Canvas", "Green to Ripe Sequence", "MVC Build Sheets", "One Group Audit Checklist",\n                    "Ascension Map", "Growth Scorecard", "Big 3 Planning Canvas", "Insight Call Script",\n                    "Buyer Signal Cheat Sheet", "7-Scenario DM Playbook", "ICP Builder", "10 Pillars of Offer Doc",\n                    "CVJ Audit", "Step LTV Benchmark", "Bottleneck Hunter"]\n',
        1,
    ),
]
EXPECTED_CAPS = ['STORM', 'CVJ', 'AVOCADO', 'SIPE', 'VAGEL', 'TTB', 'FIBS', 'F.I.B.S', 'ECAFI']
EXPECTED_NAMES = ['Hormozi', 'Kallaway', 'Cattoni', 'Tutton', 'Belcher', 'Rohan', 'Value Equation', 'Pain Stack', 'Tiny Yeses', 'DM Doctor', 'Offer Architect', 'Community OS', 'Content Engine', 'Dream Customer', 'Dream Follower', 'Hook Mastery', 'Anti-viral', 'Launch Planner', '21-day launch map', 'Customer Value Journey', 'Jim Hamilton', 'Todd Brown', 'Kevin Rogers', 'Chris Rocheleau', 'Bart Schutz', 'DigitalMarketer', 'Alex Cattoni', 'Bullet Campaign', 'Message Mapping', 'Copywriting Crossroads', 'Email Storyselling', 'Write and Ignite', 'Predictable Sales System', 'Predictable Sales Canvas', 'Ready Now Funnel', 'Flood Your Funnel', 'Self Liquidating Offer', 'Trial Upgrade Offer', 'Value Journey', 'Before After Grid', 'Gain Logic Fear', 'Indoctrination Series', 'Social Media Scorecards', 'Lead Magnet Builder', 'Qualified Email', 'S.O.U.L.F.U.L', 'S.I.P.E', 'R.I.P.E', 'Content Cannon', 'Objection Akido', 'Value Ladder Canvas', 'Perfect Offer Builder', 'Million Dollar Message', 'Core Message Canvas', 'Green to Ripe Sequence', 'MVC Build Sheets', 'One Group Audit Checklist', 'Ascension Map', 'Growth Scorecard', 'Big 3 Planning Canvas', 'Insight Call Script', 'Buyer Signal Cheat Sheet', '7-Scenario DM Playbook', 'ICP Builder', '10 Pillars of Offer Doc', 'CVJ Audit', 'Step LTV Benchmark', 'Bottleneck Hunter']

PHRASES = [
    ("Use the S.O.U.L.F.U.L. method", True), ("the R.I.P.E. Formula", True), ("Try S.I.P.E. in DMs", True),
    ("Run ECAFI", True), ("Build a content cannon", True), ("Read Alex Cattoni", True), ("hormozi says", True),
    ("F.I.B.S works", True), ("Map your value journey", True), ("Use the STORM plan", True),
    ("Our 7-Scenario DM Playbook", True), ("10 Pillars of Offer Doc", True), ("Do a CVJ Audit", True),
    ("a storm came", False), ("brainstorm ideas", False), ("Your big idea is strong", False),
    ("Plan your editorial calendar", False), ("Send 100 messages a day", False), ("ripe fruit", False),
    ("Write your welcome post", False),
]


def decode(s):
    return s.replace("@LT@", LT).replace("@GT@", GT).replace("@AMP@", chr(38))


def fail(msg):
    print("ABORT: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def read(path):
    raw = open(path, "rb").read().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def apply(text, which):
    for f, name, old, new, expected in ANCHORS:
        if f != which:
            continue
        old, new = decode(old), decode(new)
        n = text.count(old)
        print("  %-30s found %d (expected %d)" % (name, n, expected))
        if n != expected:
            fail("anchor '" + name + "' count is " + str(n) + ", expected " + str(expected))
        text = text.replace(old, new)
    return text


def py_lists(main_out):
    caps = ast.literal_eval(re.search(r"^_E3_JARGON_CAPS = (\[.*?\])", main_out, re.M | re.S).group(1))
    names = ast.literal_eval(re.search(r"^_E3_JARGON_NAMES = (\[.*?\])\s*$", main_out, re.M | re.S).group(1))
    return caps, names


def js_line(html_out, prefix):
    lines = [l for l in html_out.split("\n") if l.startswith(prefix)]
    if len(lines) != 1:
        fail("expected one line starting with " + prefix)
    return lines[0]


def js_lists(html_out):
    caps = json.loads(js_line(html_out, "const BF_JARGON_CAPS=")[len("const BF_JARGON_CAPS="):].rstrip(";"))
    names = json.loads(js_line(html_out, "const BF_JARGON_NAMES=")[len("const BF_JARGON_NAMES="):].rstrip(";"))
    return caps, names


def check_lists(main_out, html_out):
    pc, pn = py_lists(main_out)
    jc, jn = js_lists(html_out)
    if pc != EXPECTED_CAPS or jc != EXPECTED_CAPS:
        fail("CAPS lists differ from the expected 9")
    if pn != EXPECTED_NAMES or jn != EXPECTED_NAMES:
        fail("NAMES lists differ from the expected 68 (or order differs)")
    low = [w.lower() for w in pc + pn]
    if len(set(low)) != len(low):
        fail("duplicate jargon word")
    if "big idea" in low or "editorial calendar" in low:
        fail("Big Idea / Editorial Calendar must stay out")
    print("  lists: main.py and chat_test.html identical, 9 + 68 = 77, same order, no duplicates")
    return pc, pn


def py_results(main_out, caps, names):
    m = re.search(r"def _e3_has_jargon\(s\):.*?return bool\(re\.search\(caps, s\) or re\.search\(names, s\)\)", main_out, re.S)
    if not m:
        fail("could not find _e3_has_jargon")
    ns = {"re": re, "_E3_JARGON_CAPS": caps, "_E3_JARGON_NAMES": names}
    exec(m.group(0), ns)
    return [bool(ns["_e3_has_jargon"](p)) for p, _ in PHRASES]


def check_plain_rule(main_out, caps, names):
    m = re.search(r"def _f3_banned_words\(\):.*?\n\n\ndef _f3_plain_rule\(\):.*?\.\"\)\n", main_out, re.S)
    if not m:
        fail("could not find _f3_plain_rule")
    ns = {"_E3_JARGON_CAPS": caps, "_E3_JARGON_NAMES": names}
    exec(m.group(0), ns)
    rule = ns["_f3_plain_rule"]()
    if not all(w in rule for w in ("ECAFI", "S.O.U.L.F.U.L", "Bottleneck Hunter")):
        fail("plain rule does not list the new words")
    print("  coach prompt rule lists all 77 words")


def node_run(node, js):
    fd, tmp = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(js)
        return subprocess.run([node, tmp], capture_output=True, text=True), tmp
    finally:
        pass


def check_parity(main_out, html_out, caps, names):
    py = py_results(main_out, caps, names)
    want = [w for _, w in PHRASES]
    if py != want:
        bad = [PHRASES[i][0] for i in range(len(want)) if py[i] != want[i]]
        fail("Python grader check gives unexpected results on: " + str(bad))
    node = shutil.which("node")
    if not node:
        print("  WARNING: node not found, JavaScript parity check and node --check skipped")
        print("  Python check: " + str(len(PHRASES)) + " phrases as expected")
        return
    keep = ("const BF_JARGON_CAPS=", "const BF_JARGON_NAMES=", "function bfAlt(", "const BF_CAPS_RE=",
            "const BF_NAMES_RE=", "function bfHasJargon(")
    src = "\n".join(js_line(html_out, k) for k in keep)
    js = src + "\nconst P=" + json.dumps([p for p, _ in PHRASES]) + ";\nconsole.log(JSON.stringify(P.map(bfHasJargon)));\n"
    r, tmp = node_run(node, js)
    os.remove(tmp)
    if r.returncode != 0:
        fail("node could not run the frontend check:\n" + r.stderr[-1000:])
    js_res = json.loads(r.stdout.strip())
    if js_res != py:
        bad = [PHRASES[i][0] for i in range(len(py)) if js_res[i] != py[i]]
        fail("Python and JavaScript disagree on: " + str(bad))
    print("  parity: Python and JavaScript agree on all " + str(len(PHRASES)) + " phrases, all as expected")


def node_check(html_out):
    node = shutil.which("node")
    if not node:
        return
    pat = re.compile(LT + r"script(?![^" + GT + r"]*\bsrc=)[^" + GT + r"]*" + GT + r"(.*?)" + LT + r"/script" + GT, re.S | re.I)
    blocks = pat.findall(html_out)
    if not blocks:
        fail("no inline script block found")
    for i, js in enumerate(blocks, 1):
        fd, tmp = tempfile.mkstemp(suffix=".js")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(js)
            r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                fail("node --check failed on script block " + str(i) + ":\n" + r.stderr[-1500:])
        finally:
            os.remove(tmp)
    print("  node --check OK (" + str(len(blocks)) + " script block(s))")


def write_temp(path, text, crlf):
    data = (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".brickF3c-", dir=os.path.dirname(os.path.abspath(path)))
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    shutil.copymode(path, tmp)
    return tmp


def main():
    ap = argparse.ArgumentParser(description="Brick F.3c: one jargon list on both sides")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    main_path = os.path.join(args.dir, "main.py")
    html_path = os.path.join(args.dir, "chat_test.html")
    for p in (main_path, html_path):
        if not os.path.isfile(p):
            fail(os.path.basename(p) + " not found in " + os.path.abspath(args.dir))
    main_text, main_crlf = read(main_path)
    html_text, html_crlf = read(html_path)
    if MARKER in main_text or MARKER in html_text:
        fail("Brick F.3c is already applied (second run refused)")
    if "BRICK F.3" not in main_text:
        fail("BRICK F.3 not found in main.py. Apply Brick F.3 first.")
    if "BRICK F.2a" not in html_text:
        fail("BRICK F.2a not found in chat_test.html. Apply Brick F.2a first.")
    print("main.py: " + main_path + (" (CRLF)" if main_crlf else ""))
    print("chat_test.html: " + html_path + (" (CRLF)" if html_crlf else ""))
    print("Anchors:")
    html_out = apply(html_text, "html")
    main_out = apply(main_text, "main")
    print("Checks:")
    for name, before, after in (("main.py", main_text, main_out), ("chat_test.html", html_text, html_out)):
        for t in TOKENS:
            if t in after:
                fail("token " + t + " left in " + name)
        if [c for c in set(after) - set(before) if not c.isascii()]:
            fail("non-ASCII text added to " + name)
    if main_out.count(MARKER) != 1 or html_out.count(MARKER) != 1:
        fail("marker count is wrong")
    if "framework names as they are" in html_out:
        fail("old Arabic rule still present")
    print("  markers present, Arabic rule updated")
    caps, names = check_lists(main_out, html_out)
    check_plain_rule(main_out, caps, names)
    check_parity(main_out, html_out, caps, names)
    node_check(html_out)
    tmp_main = write_temp(main_path, main_out, main_crlf)
    tmp_html = None
    try:
        try:
            py_compile.compile(tmp_main, doraise=True, cfile=tmp_main + "c")
        except py_compile.PyCompileError as e:
            fail("py_compile failed: " + str(e))
        finally:
            if os.path.exists(tmp_main + "c"):
                os.remove(tmp_main + "c")
        print("  py_compile OK")
        if args.dry_run:
            print("DRY RUN: all checks passed. Nothing was written.")
            return
        tmp_html = write_temp(html_path, html_out, html_crlf)
        for p in (main_path, html_path):
            bak = p + ".bak-brickF3c"
            if os.path.exists(bak):
                print("Backup already exists, kept as is: " + bak)
            else:
                shutil.copy2(p, bak)
                print("Backup: " + bak)
        os.replace(tmp_main, main_path)
        tmp_main = None
        try:
            os.replace(tmp_html, html_path)
            tmp_html = None
        except Exception as e:
            shutil.copy2(main_path + ".bak-brickF3c", main_path)
            fail("chat_test.html write failed (" + str(e) + "). main.py restored from backup.")
        print("DONE: Brick F.3c applied. Restart FastAPI and hard refresh the browser.")
    finally:
        for t in (tmp_main, tmp_html):
            if t and os.path.exists(t):
                os.remove(t)


if __name__ == "__main__":
    main()
