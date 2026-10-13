#!/usr/bin/env python3
"""
BRICK E3.1: RELAXED STANDUP MINIMUM + MISSING ITEMS
===================================================

What it does
------------
Small follow-up to Brick E3 (fair standup). Patches two files:

main.py
  * Adds  missing_items  to the /api/standup response: a list of
    {key, label, index?} objects saying, in plain words, what is still missing:
      - work     : the work text is under 15 characters and under 3 words
      - link     : the task needs a link and none starting with http(s) was given
      - numbers  : the task needs numbers and the Numbers field has no digit
      - part     : a task part the grader says is missing (grader MISSING line)
    missing_items never changes the score. Any error returns an empty list.
  * Grader prompt: the task parts are now numbered, and the grader adds one
    extra line,  MISSING: 2, 3  (or none). Scoring, plain language rules and
    the REASON / HINT / NEXT lines are unchanged. No beginner gating.
  * StandupRequest is NOT changed.

chat_test.html
  * Minimum before grading, for every user (guided or not):
    15 characters OR 3 words. Replaces the 100-character rule.
  * Counter and field label updated to match.
  * The failed-result screen shows a short "Still missing" list.
  * The last result is kept in  E3.last  (score, reason, hint, missing_items)
    for Brick F.

Safety
------
  * Refuses unless both files contain BRICK E1 and BRICK E3.
  * Refuses a second run (BRICK E3.1 marker in either file).
  * Every anchor must be found exactly expected_count times, or nothing is written.
  * Tokens in this file:  @LT@ = less-than,  @GT@ = greater-than,  @AMP@ = ampersand.
  * Checks before writing: main.py is compiled with Python; the app script in
    chat_test.html is checked with  node --check  (skipped with a warning if
    node is not installed).
  * Backups: main.py.bak-brickE31 and chat_test.html.bak-brickE31 (never overwritten).
  * Atomic writes (temp file + fsync + os.replace). If the second file fails,
    the first one is restored from its backup.

Usage
-----
    cd /root/e5-ai-coach
    python3 patch_brickE31.py --dry-run     # checks only
    python3 patch_brickE31.py               # apply
    python3 patch_brickE31.py --dir /root/e5-ai-coach
Then restart the FastAPI server and hard-refresh the browser.

Rollback
--------
    cp main.py.bak-brickE31 main.py
    cp chat_test.html.bak-brickE31 chat_test.html
"""
# BRICK E3.1: RELAXED STANDUP MINIMUM + MISSING ITEMS

import os
import re
import sys
import shutil
import tempfile
import subprocess

MARKER = "BRICK E3.1"
PREREQ_MARKERS = ["BRICK E1", "BRICK E3"]
BACKUP_SUFFIX = ".bak-brickE31"
MAIN_FILE = "main.py"
HTML_FILE = "chat_test.html"

LT, GT, AMP = chr(60), chr(62), chr(38)
TOKENS = [("@LT@", LT), ("@GT@", GT), ("@AMP@", AMP)]


def decode(s):
    for tok, ch in TOKENS:
        s = s.replace(tok, ch)
    return s


# ---------------------------------------------------------------------------
# Anchors: (name, old, new, expected_count)
# ---------------------------------------------------------------------------

MAIN_ANCHORS = [
    (
        'main: E3.1 helpers before the standup route',
        '# --- STANDUP ---',
        r'''# ===== BRICK E3.1: relaxed standup minimum + missing_items in the /api/standup response =====
# missing_items lists what is still missing, in plain words. It never changes the score.
# Server checks: work too short, link (only if the task needs one), numbers (only if needed).
# AI check: the grader's MISSING line gives the numbers of the task parts not yet covered.
import operator as _op31

_E31_MIN_CHARS = 15
_E31_MIN_WORDS = 3


def _e31_work_ok(text):
    s = str(text or "").strip()
    return _op31.ge(len(s), _E31_MIN_CHARS) or _op31.ge(len(s.split()), _E31_MIN_WORDS)


def _e31_missing_parts(raw, deliverables):
    line = _e3_line(raw, "MISSING")
    if not line or re.match(r"(?i)\s*(none|nothing|no|n/a|-)(\W|$)", line):
        return []
    out = []
    for m in re.findall(r"\d+", line):
        i = int(m)
        if i in range(1, len(deliverables) + 1) and i not in out:
            out.append(i)
    return out[:10]


def _e31_missing_items(raw, task, rubric, link_ok, numbers_ok, asset_text):
    try:
        items = []
        if not _e31_work_ok(asset_text):
            items.append({"key": "work", "label": "A few clear lines about what you did"})
        if rubric.get("link") and not link_ok:
            items.append({"key": "link", "label": "A link to your work (starting with http:// or https://)"})
        if rubric.get("metrics") and not numbers_ok:
            items.append({"key": "numbers", "label": "Your real numbers, for example views, replies or sales"})
        deliverables = [str(d) for d in (task.get("deliverables") or [])]
        for i in _e31_missing_parts(raw, deliverables):
            label = deliverables[i - 1].strip()[:200]
            if label and not _e3_has_jargon(label):
                items.append({"key": "part", "index": i, "label": label})
            elif label:
                items.append({"key": "part", "index": i, "label": "Part " + str(i) + " of this task"})
        return items
    except Exception:
        return []
# ===== end BRICK E3.1 helpers =====


# --- STANDUP ---''',
        1,
    ),
    (
        'main: number the task parts in the grader prompt',
        '    parts = N.join("- " + str(d) for d in task.get("deliverables", [])) or "- (no list given)"',
        '    parts = N.join(str(i + 1) + ". " + str(d) for i, d in enumerate(task.get("deliverables", []))) or "- (no list given)"  # BRICK E3.1',
        1,
    ),
    (
        'main: grader outputs 5 lines',
        '"OUTPUT exactly these 4 lines and nothing else:",',
        '"OUTPUT exactly these 5 lines and nothing else:",',
        1,
    ),
    (
        'main: grader MISSING line',
        '        "NEXT: one short sentence, what to do once this task is done",',
        r'''        "NEXT: one short sentence, what to do once this task is done",
        "MISSING: the numbers of the parts above that are missing or too thin, separated by commas, or none",  # BRICK E3.1''',
        1,
    ),
    (
        'main: compute missing_items after the review text',
        '    review = _e3_review_text(score, e3_reason, e3_hint, e3_next)',
        r'''    review = _e3_review_text(score, e3_reason, e3_hint, e3_next)
    e3_missing = _e31_missing_items(raw_review, task, rubric, link_ok, numbers_ok, req.asset_text)  # BRICK E3.1''',
        1,
    ),
    (
        'main: return missing_items',
        '"next_step": e3_next, "rubric": rubric,',
        '"next_step": e3_next, "missing_items": e3_missing, "rubric": rubric,',
        1,
    ),
]

HTML_ANCHORS = [
    (
        'html: replace 100-char counter with E3.1 helpers',
        "function e3CounterText(n){if(guidedOn())return n?n+' characters':'A few clear lines are enough.';return n+' characters · '+(n@LT@100?(100-n)+' more needed':'ready to submit');}",
        r'''// ===== BRICK E3.1: relaxed standup minimum for everyone (15 characters or 3 words) + missing items on the result screen =====
function e31Words(s){return String(s==null?'':s).trim().split(/\s+/).filter(Boolean).length;}
function e31MinOk(s){s=String(s==null?'':s).trim();return s.length@GT@=15||e31Words(s)@GT@=3;}
function e3CounterText(s){s=String(s==null?'':s).trim();const n=s.length;if(!n)return 'A few clear lines are enough.';return n+' characters · '+(e31MinOk(s)?'ready to submit':'add a few more words');}
function e31MissingHTML(d,pass){const list=Array.isArray(d@AMP@@AMP@d.missing_items)?d.missing_items:[];E3.last={score:d@AMP@@AMP@d.score,reason:d@AMP@@AMP@d.reason,hint:d@AMP@@AMP@d.hint,missing_items:list};if(pass||!list.length)return '';return '@LT@div class="mt"@GT@@LT@b@GT@Still missing:@LT@/b@GT@@LT@ul@GT@'+list.map(x=@GT@'@LT@li@GT@'+esc(e3Plain(x@AMP@@AMP@typeof x==='object'?x.label:x))+'@LT@/li@GT@').join('')+'@LT@/ul@GT@@LT@/div@GT@';}
// ===== end BRICK E3.1 helpers =====''',
        1,
    ),
    (
        'html: field label',
        "'Your work (minimum 100 characters)'",
        "'Your work (a few clear lines)'",
        1,
    ),
    (
        'html: counter on modal open',
        "e3CounterText(String(d.text||'').trim().length)",
        "e3CounterText(String(d.text||''))",
        1,
    ),
    (
        'html: counter while typing',
        "const n=e.target.value.trim().length;$('#standupCounter').textContent=e3CounterText(n);",
        "$('#standupCounter').textContent=e3CounterText(e.target.value);",
        1,
    ),
    (
        'html: submit minimum for everyone',
        r''' if(guidedOn()){if(!text)throw new Error('Write a few words about what you did.');}
 else if(text.length@LT@100)throw new Error('Add at least 100 characters explaining your work.');''',
        " if(!e31MinOk(text))throw new Error('Write a few words about what you did (at least 3 words).'); // BRICK E3.1",
        1,
    ),
    (
        'html: result body opens group',
        ' const body=(reason||hint||next)?',
        ' const body=((reason||hint||next)?',
        1,
    ),
    (
        'html: result body adds missing list',
        ':`@LT@div class="md"@GT@${md(d.review||\'Review received.\')}@LT@/div@GT@`;',
        ':`@LT@div class="md"@GT@${md(d.review||\'Review received.\')}@LT@/div@GT@`)+e31MissingHTML(d,pass); // BRICK E3.1',
        1,
    ),
]


# ---------------------------------------------------------------------------

def fail(msg):
    print("ERROR: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def apply_anchors(label, src, anchors):
    nl = "\r\n" if "\r\n" in src else "\n"
    out, bad = src, []
    for name, old, new, expected in anchors:
        old_d = decode(old).replace("\n", nl)
        new_d = decode(new).replace("\n", nl)
        count = src.count(old_d)
        ok = count == expected
        print(("OK   " if ok else "FAIL ") + label + " | " + name + ": found " + str(count) + ", expected " + str(expected))
        if not ok:
            bad.append(name)
            continue
        out = out.replace(old_d, new_d, expected)
    return out, bad


def check_python(text):
    try:
        compile(text, MAIN_FILE, "exec")
    except SyntaxError as exc:
        fail("patched main.py does not compile: " + str(exc))
    print("OK   check | main.py compiles")


def check_js(html, folder):
    open_tag = LT + 'script id="creator-os-app"' + GT
    close_tag = LT + "/script" + GT
    start = html.find(open_tag)
    end = html.find(close_tag, start + 1) if start != -1 else -1
    if start == -1 or end == -1:
        fail("could not find the creator-os-app script block in chat_test.html")
    node = shutil.which("node")
    if not node:
        print("WARN check | node not installed: JavaScript syntax check skipped")
        return
    fd, tmp = tempfile.mkstemp(prefix=".brickE31-check-", suffix=".js", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html[start + len(open_tag):end])
        res = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
    finally:
        os.remove(tmp)
    if res.returncode != 0:
        fail("patched chat_test.html app script has a syntax error:" + chr(10) + (res.stderr or res.stdout)[-1500:])
    print("OK   check | chat_test.html app script passes node --check")


def atomic_write(path, text):
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".brickE31-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(argv):
    dry_run = "--dry-run" in argv
    folder = os.getcwd()
    if "--dir" in argv:
        i = argv.index("--dir")
        if i + 1 == len(argv):
            fail("--dir needs a folder")
        folder = argv[i + 1]
    folder = os.path.abspath(folder)
    main_path = os.path.join(folder, MAIN_FILE)
    html_path = os.path.join(folder, HTML_FILE)
    print("BRICK E3.1 patch -- folder: " + folder)

    for p in (main_path, html_path):
        if not os.path.isfile(p):
            fail("file not found: " + p)
    main_src, html_src = read(main_path), read(html_path)

    # 1. Refuse a second run
    for label, src in ((MAIN_FILE, main_src), (HTML_FILE, html_src)):
        if MARKER in src:
            fail(MARKER + " marker already present in " + label + ". Already applied (or half applied: restore both .bak-brickE31 files).")

    # 2. Prerequisites
    for label, src in ((MAIN_FILE, main_src), (HTML_FILE, html_src)):
        for m in PREREQ_MARKERS:
            if m not in src:
                fail("prerequisite missing in " + label + ": '" + m + "'. Apply it first.")
    print("OK   prerequisites: " + ", ".join(PREREQ_MARKERS) + " in both files")

    # 3. Anchors (all verified before anything is written)
    main_out, bad_main = apply_anchors(MAIN_FILE, main_src, MAIN_ANCHORS)
    html_out, bad_html = apply_anchors(HTML_FILE, html_src, HTML_ANCHORS)
    if bad_main or bad_html:
        fail("anchor mismatch: " + ", ".join(bad_main + bad_html))

    # 4. Post-checks
    for label, out in ((MAIN_FILE, main_out), (HTML_FILE, html_out)):
        if MARKER not in out:
            fail("post-check: marker missing in patched " + label)
        for tok, _ in TOKENS:
            if tok in out:
                fail("post-check: undecoded token " + tok + " in patched " + label)
    if "100 characters" in html_out:
        fail("post-check: a 100-character rule is still in chat_test.html")
    check_python(main_out)
    check_js(html_out, folder)

    if dry_run:
        print("DRY RUN -- all checks passed, nothing written.")
        return

    # 5. Backups (never overwrite)
    backups = [(main_path, main_path + BACKUP_SUFFIX), (html_path, html_path + BACKUP_SUFFIX)]
    for _, b in backups:
        if os.path.exists(b):
            fail("backup already exists: " + b + " -- move or delete it, then rerun.")
    for src_path, b in backups:
        shutil.copy2(src_path, b)
        print("OK   backup: " + b)

    # 6. Atomic writes
    try:
        atomic_write(main_path, main_out)
    except Exception as exc:
        fail("could not write main.py (original untouched): " + str(exc))
    try:
        atomic_write(html_path, html_out)
    except Exception as exc:
        shutil.copy2(main_path + BACKUP_SUFFIX, main_path)
        fail("could not write chat_test.html (" + str(exc) + "). main.py was restored from its backup.")

    print("DONE BRICK E3.1 applied. Restart the FastAPI server, then hard-refresh the browser.")


if __name__ == "__main__":
    main(sys.argv[1:])
