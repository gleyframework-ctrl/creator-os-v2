#!/usr/bin/env python3
"""
BRICK F.1: LANGUAGE FIX FOR THE BRICK F COACH PANEL
===================================================

What it does
------------
In main.py, inside _bf_system_prompt (used only when mode == "standup_fix"),
replaces the rule

    "- Write in the same language as their text.",

with a marker comment and an English-by-default rule:

    # BRICK F.1: language fix
    "- Write in English by default. Only write in another language if the user's own text is clearly and mostly in that language.",

"mostly" (not "entirely") so Arabic standups that contain English words
(TikTok, URLs, brand names) are still answered in Arabic.
Nothing else in main.py changes. chat_test.html is not touched.

Safety
------
  * Refuses unless the BRICK F marker is in main.py.
  * Refuses a second run (BRICK F.1 already in main.py).
  * The anchor line must be found exactly once, or nothing is written.
  * Backup: main.py.bak-brickF1 (never overwritten).
  * The patched file is written to a temp file, checked with py_compile,
    fsynced, then swapped in with os.replace (atomic).
  * ASCII only. No angle brackets.

Usage
-----
    cd /root/e5-ai-coach
    python3 patch_brickF1.py --dry-run
    python3 patch_brickF1.py
    python3 patch_brickF1.py --dir /root/e5-ai-coach
Then restart the FastAPI server.

Rollback
--------
    cp main.py.bak-brickF1 main.py
"""
# BRICK F.1: language fix

import os
import sys
import shutil
import tempfile
import py_compile

MARKER = "BRICK F.1"
PREREQ = "BRICK F: EMBEDDED COACH IN TRY AGAIN"
TARGET = "main.py"
BACKUP_SUFFIX = ".bak-brickF1"

INDENT = " " * 12
OLD = INDENT + '"- Write in the same language as their text.",'
NEW = (INDENT + "# BRICK F.1: language fix" + "\n"
       + INDENT + '"- Write in English by default. Only write in another language'
       + " if the user's own text is clearly and mostly in that language.\",")
EXPECTED = 1


def fail(msg):
    print("ERROR: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def py_check(path):
    cache_dir = tempfile.mkdtemp(prefix="brickF1-pyc-")
    try:
        py_compile.compile(path, cfile=os.path.join(cache_dir, "main.pyc"), doraise=True)
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def main(argv):
    dry_run = "--dry-run" in argv
    folder = os.getcwd()
    if "--dir" in argv:
        i = argv.index("--dir")
        if i + 1 == len(argv):
            fail("--dir needs a folder")
        folder = argv[i + 1]
    path = os.path.join(os.path.abspath(folder), TARGET)
    backup = path + BACKUP_SUFFIX
    print("BRICK F.1 patch -- target: " + path)

    if not os.path.isfile(path):
        fail("file not found")
    with open(path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1. Refuse a second run
    if MARKER in src:
        fail(MARKER + " marker already present. Already applied.")

    # 2. Prerequisite
    if PREREQ not in src:
        fail("prerequisite missing: BRICK F is not in main.py. Apply Brick F first.")
    print("OK   prerequisite: BRICK F")

    # 3. Anchor (line-ending safe)
    nl = "\r\n" if "\r\n" in src else "\n"
    old = OLD + nl
    new = NEW.replace("\n", nl) + nl
    count = src.count(old)
    print(("OK   " if count == EXPECTED else "FAIL ") + "anchor 'language rule in _bf_system_prompt': found "
          + str(count) + ", expected " + str(EXPECTED))
    if count != EXPECTED:
        fail("anchor count mismatch")
    out = src.replace(old, new, 1)

    # 4. Post-checks
    if MARKER not in out or out.count(MARKER) != 1:
        fail("post-check: marker should appear exactly once after patching")
    if not (NEW.isascii() and open(os.path.abspath(__file__), encoding="utf-8").read().isascii()):
        fail("post-check: non-ASCII text in the patch")
    if len(out.splitlines()) != len(src.splitlines()) + 1:
        fail("post-check: expected exactly one added line")

    # 5. Write temp file, compile it
    fd, tmp = tempfile.mkstemp(prefix=".brickF1-", suffix=".py", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
            f.flush()
            os.fsync(f.fileno())
        try:
            py_check(tmp)
        except py_compile.PyCompileError as exc:
            fail("patched main.py does not compile: " + str(exc))
        print("OK   check | patched main.py passes py_compile")

        if dry_run:
            print("DRY RUN -- all checks passed, nothing written.")
            return

        # 6. Backup (never overwrite)
        if os.path.exists(backup):
            fail("backup already exists: " + backup + " -- move or delete it, then rerun.")
        shutil.copy2(path, backup)
        print("OK   backup: " + backup)

        # 7. Atomic swap
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    print("DONE BRICK F.1 applied. Restart the FastAPI server.")


if __name__ == "__main__":
    main(sys.argv[1:])
