#!/usr/bin/env python3
"""
patch_brickF2a.py - Brick F.2a: Progress subtitle shows the 5-phase model (chat_test.html only)

What it does
  F2a-1  Progress subtitle:
         old  Foundation to Traffic to Conversion. Start focused work; submit real evidence.
         new  Foundation to Product to Community to Traffic to Retention. Start focused work; submit real evidence.
         The arrow is the same Unicode arrow (U+2192) the file already uses.

Safety
  - Needs BRICK G in main.py (5-phase model live). Refuses a second run.
  - Anchor counted before anything is written (expected 1).
  - node --check on every inline script block (skipped with a warning if node is not installed).
  - Backup chat_test.html.bak-brickF2a (never overwritten). Atomic write. CRLF safe.

Usage
  python3 patch_brickF2a.py --dry-run
  python3 patch_brickF2a.py
  python3 patch_brickF2a.py --dir /root/e5-ai-coach

Rollback
  cp chat_test.html.bak-brickF2a chat_test.html   then hard refresh the browser
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

MARKER = "BRICK F.2a"
PREREQ = "BRICK G"
LT, GT, ARROW = chr(60), chr(62), chr(0x2192)

ANCHORS = [
    (
        "F2a-1 Progress subtitle",
        "V.journey={title:'Progress',sub:'Foundation @A@ Traffic @A@ Conversion. Start focused work; submit real evidence.',",
        "/* BRICK F.2a: 5-phase subtitle */V.journey={title:'Progress',sub:'Foundation @A@ Product @A@ Community @A@ Traffic @A@ Retention. Start focused work; submit real evidence.',",
        1,
    ),
]


def decode(s):
    return s.replace("@A@", ARROW).replace("@LT@", LT).replace("@GT@", GT).replace("@AMP@", chr(38))


def fail(msg):
    print("ABORT: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def node_check(html):
    node = shutil.which("node")
    if not node:
        print("  WARNING: node not found, node --check skipped")
        return
    pat = re.compile(LT + r"script(?![^" + GT + r"]*\bsrc=)[^" + GT + r"]*" + GT + r"(.*?)" + LT + r"/script" + GT, re.S | re.I)
    blocks = pat.findall(html)
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


def main():
    ap = argparse.ArgumentParser(description="Brick F.2a: 5-phase Progress subtitle")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    html_path = os.path.join(args.dir, "chat_test.html")
    main_path = os.path.join(args.dir, "main.py")
    for p in (html_path, main_path):
        if not os.path.isfile(p):
            fail(os.path.basename(p) + " not found in " + os.path.abspath(args.dir))
    if PREREQ not in open(main_path, encoding="utf-8").read():
        fail("BRICK G not found in main.py. Apply Brick G first.")
    raw = open(html_path, "rb").read().decode("utf-8")
    if MARKER in raw:
        fail("Brick F.2a is already applied to chat_test.html (second run refused)")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    print("chat_test.html: " + html_path + (" (CRLF)" if crlf else ""))
    print("Anchors:")
    out = text
    for name, old, new, expected in ANCHORS:
        old, new = decode(old), decode(new)
        n = out.count(old)
        print("  %-26s found %d (expected %d)" % (name, n, expected))
        if n != expected:
            fail("anchor '" + name + "' count is " + str(n) + ", expected " + str(expected))
        out = out.replace(old, new)
    print("Checks:")
    if out.count(MARKER) != 1:
        fail("marker count is not 1")
    if "Foundation " + ARROW + " Traffic " + ARROW + " Conversion" in out:
        fail("old subtitle still present")
    if "@A@" in out or "@LT@" in out:
        fail("token left in output")
    print("  marker present, old subtitle gone")
    node_check(out)
    if args.dry_run:
        print("DRY RUN: all checks passed. Nothing was written.")
        return
    final = out.replace("\n", "\r\n") if crlf else out
    bak = html_path + ".bak-brickF2a"
    fd, tmp = tempfile.mkstemp(prefix=".brickF2a-", suffix=".html", dir=os.path.dirname(os.path.abspath(html_path)))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(final.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(bak):
            print("Backup already exists, kept as is: " + bak)
        else:
            shutil.copy2(html_path, bak)
            print("Backup: " + bak)
        shutil.copymode(html_path, tmp)
        os.replace(tmp, html_path)
        tmp = None
        print("DONE: Brick F.2a applied. Hard refresh the browser.")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
