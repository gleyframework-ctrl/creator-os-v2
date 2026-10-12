#!/usr/bin/env python3
"""
patch_brickF4.py - Brick F.4: guided mode stays on for everyone (main.py + chat_test.html)

What it does (5 anchors, each expected once)
  A1  chat_test.html guidedOn(): the 2-task cutoff is removed. Guided mode is on for every
      signed-in user until they turn it off with Show all tools (S.ui.showAll, per device).
  A2  chat_test.html: the guidedOn() comment matches the new rule.
  A3  chat_test.html Settings help text: "Guided mode shows one move at a time. It stays on
      until you turn it off here. Applies to this device only."
  B1  main.py _b5_beginner_on(): the task cutoff is removed. Still needs beginner = true
      from the browser.
  B2  main.py B5_GUIDED_TASK_LIMIT kept, marked "no longer used".
  Not touched: prompt text, grader, standup, E3, F, F.1, F.3, F.3c, S.ui.showAll behavior.

Safety
  - Needs BRICK F.3c in both files. Refuses a second run (BRICK F.4 in either file).
  - Every anchor is counted before anything is written.
  - Old logic must be gone: Math.min(c,2) and tasks_completed_count not in guidedOn(),
    B5_GUIDED_TASK_LIMIT only in its definition line.
  - guidedOn() run in node with test values, _b5_beginner_on() run in Python with test values.
  - py_compile and node --check (node checks skipped with a warning if node is missing).
  - Backups .bak-brickF4 (never overwritten). Atomic two-file write, main.py restored if
    the second write fails. CRLF safe.

Usage
  python3 patch_brickF4.py --dry-run
  python3 patch_brickF4.py
  python3 patch_brickF4.py --dir /root/e5-ai-coach

Rollback
  cp main.py.bak-brickF4 main.py
  cp chat_test.html.bak-brickF4 chat_test.html
  then restart FastAPI and hard refresh the browser
"""
import argparse
import json
import operator
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

MARKER = "BRICK F.4"
PREREQ = "BRICK F.3c"
TOKENS = ("@LT@", "@GT@", "@AMP@")
LT, GT = chr(60), chr(62)

ANCHORS = [
    (
        'html',
        'A1 guidedOn() no task cutoff',
        '  const j=S.main.journey;const c=isObj(j)?Math.max(0,Math.floor(num(j.tasks_completed_count))):0;\n  return Math.min(c,2)!==2;\n',
        '  return true; // BRICK F.4: no task cutoff. Off only via Show all tools (S.ui.showAll).\n',
        1,
    ),
    (
        'html',
        'A2 guidedOn() comment',
        '// B. Guided mode: signed in, fewer than 2 completed tasks, and not switched off on this device.\n// While the journey is loading, the cached journey decides; with no cache, guided mode is on.\n',
        '// B. Guided mode (BRICK F.4): signed in and not switched off on this device. No task cutoff.\n',
        1,
    ),
    (
        'html',
        'A3 Settings help text',
        'Guided mode shows one move at a time until your first two tasks are complete. Applies to this device only.',
        'Guided mode shows one move at a time. It stays on until you turn it off here. Applies to this device only.',
        1,
    ),
    (
        'main',
        'B1 _b5_beginner_on no cutoff',
        '        done = journey.get("tasks_completed") if isinstance(journey, dict) else None\n        return _op5.lt(len(done or []), B5_GUIDED_TASK_LIMIT)\n',
        '        # BRICK F.4: no task cutoff. The browser decides (beginner = guidedOn(), off only via Show all tools).\n        return True\n',
        1,
    ),
    (
        'main',
        'B2 limit kept for reference',
        'B5_GUIDED_TASK_LIMIT = 2\n',
        'B5_GUIDED_TASK_LIMIT = 2  # BRICK F.4: no longer used (no task cutoff), kept for reference\n',
        1,
    ),
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
        print("  %-32s found %d (expected %d)" % (name, n, expected))
        if n != expected:
            fail("anchor '" + name + "' count is " + str(n) + ", expected " + str(expected))
        text = text.replace(old, new)
    return text


def guided_src(html_out):
    m = re.search(r"function guidedOn\(\)\{\n.*?\n\}\n", html_out, re.S)
    if not m:
        fail("could not find guidedOn()")
    return m.group(0)


def beginner_src(main_out):
    m = re.search(r"def _b5_beginner_on\(req, journey\):\n.*?\n\n", main_out, re.S)
    if not m:
        fail("could not find _b5_beginner_on()")
    return m.group(0)


def check_old_logic(main_out, html_out):
    g = guided_src(html_out)
    if "Math.min(c,2)" in g or "tasks_completed_count" in g:
        fail("old task cutoff still in guidedOn()")
    if "S.ui.showAll===true" not in g or "SESSION.member_id" not in g:
        fail("guidedOn() lost the sign-in or Show all tools check")
    if main_out.count("B5_GUIDED_TASK_LIMIT") != 1 or "B5_GUIDED_TASK_LIMIT = 2  # BRICK F.4" not in main_out:
        fail("B5_GUIDED_TASK_LIMIT must appear only in its definition line")
    if "B5_GUIDED_TASK_LIMIT" in beginner_src(main_out):
        fail("_b5_beginner_on() still reads the limit")
    print("  old logic gone: no Math.min(c,2) / tasks_completed_count in guidedOn(), limit only defined")


def check_backend(main_out):
    ns = {"_op5": operator}
    exec(beginner_src(main_out), ns)
    f = ns["_b5_beginner_on"]

    class R:
        def __init__(self, **k):
            self.__dict__.update(k)
    cases = []
    for n in (0, 2, 10):
        cases.append(("beginner=True, " + str(n) + " tasks", f(R(beginner=True), {"tasks_completed": ["t"] * n}), True))
    cases.append(("beginner=False", f(R(beginner=False), {"tasks_completed": []}), False))
    cases.append(("beginner missing", f(R(), {"tasks_completed": []}), False))
    cases.append(("broken journey", f(R(beginner=True), None), True))
    cases.append(("journey not a dict", f(R(beginner=True), "x"), True))
    bad = [c[0] for c in cases if c[1] is not c[2]]
    if bad:
        fail("_b5_beginner_on() wrong on: " + str(bad))
    print("  backend: beginner=True with 0/2/10 tasks: True, false/missing: False, broken journey: True")


def check_frontend(html_out):
    node = shutil.which("node")
    if not node:
        print("  WARNING: node not found, guidedOn() test and node --check skipped")
        return False
    src = guided_src(html_out)
    js = ("function isObj(x){if(x===null)return false;if(typeof x!=='object')return false;return !Array.isArray(x);}\n"
          "function num(x){const n=Number(x);return isFinite(n)?n:0;}\n"
          "let SESSION={},S={};\n" + src +
          "const out=[];\n"
          "function run(member,showAll,count){SESSION={member_id:member};S={ui:{showAll:showAll},main:{journey:{tasks_completed_count:count}}};out.push(guidedOn());}\n"
          "run('m1',false,0);run('m1',false,2);run('m1',false,10);run('m1',undefined,2);run('m1',true,0);run('m1',true,10);run('',false,0);run(null,false,5);\n"
          "SESSION={member_id:'m1'};S={ui:{},main:{}};out.push(guidedOn());\n"
          "console.log(JSON.stringify(out));\n")
    fd, tmp = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(js)
        r = subprocess.run([node, tmp], capture_output=True, text=True)
    finally:
        os.remove(tmp)
    if r.returncode != 0:
        fail("node could not run guidedOn():\n" + r.stderr[-1000:])
    got = json.loads(r.stdout.strip())
    want = [True, True, True, True, False, False, False, False, True]
    if got != want:
        fail("guidedOn() results " + str(got) + ", expected " + str(want))
    print("  frontend: signed in with 0/2/10 tasks: true, Show all tools: false, signed out: false")
    return True


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
    fd, tmp = tempfile.mkstemp(prefix=".brickF4-", dir=os.path.dirname(os.path.abspath(path)))
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    shutil.copymode(path, tmp)
    return tmp


def main():
    ap = argparse.ArgumentParser(description="Brick F.4: guided mode stays on for everyone")
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
        fail("Brick F.4 is already applied (second run refused)")
    if PREREQ not in main_text or PREREQ not in html_text:
        fail("BRICK F.3c must be in both main.py and chat_test.html. Apply Brick F.3c first.")
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
        if MARKER not in after:
            fail("marker missing in " + name)
    if "until your first two tasks are complete" in html_out:
        fail("old Settings help text still present")
    check_old_logic(main_out, html_out)
    check_backend(main_out)
    check_frontend(html_out)
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
            bak = p + ".bak-brickF4"
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
            shutil.copy2(main_path + ".bak-brickF4", main_path)
            fail("chat_test.html write failed (" + str(e) + "). main.py restored from backup.")
        print("DONE: Brick F.4 applied. Restart FastAPI and hard refresh the browser.")
    finally:
        for t in (tmp_main, tmp_html):
            if t and os.path.exists(t):
                os.remove(t)


if __name__ == "__main__":
    main()
