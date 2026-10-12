#!/usr/bin/env python3
"""
BRICK 3.1 (backend hotfix) - calculate_trajectory uses the current task's own deadline_day.
Patches main.py only. Requires Brick 1B. Independent of the frontend patch.
  - Before or on the deadline: on_track (ahead if a later-planned task is already done). Never behind.
  - 1-2 days past the deadline: on_track, gentle "pick it up today" message.
  - 3+ days past the deadline: behind, same gentle message (no warning emoji, no yellow).

Usage:
  python3 patch_brick3_1_backend.py --check         dry run, writes nothing
  python3 patch_brick3_1_backend.py                 patch /root/e5-ai-coach/main.py
  python3 patch_brick3_1_backend.py /path/main.py   patch another copy

Copy-safety: this file contains NO less-than, greater-than or ampersand characters.
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

MARKER = "Brick 3.1: pace from the current task"
NEED = "BRICK 1B: WORKSPACE SYNC"
START = "def calculate_trajectory(journey):"
END = "\n\n# ====="
OLD_SIGN = "expected = max(1, current_day // 7)"

NEW_FN = """def calculate_trajectory(journey):
    # Brick 3.1: pace from the current task's own deadline_day. Never behind before deadline + 3 days.
    import operator
    neutral = {"status": "on_track", "message": "", "color": "blue"}
    try:
        current_day = int(journey.get("current_day", 1) or 1)
        task = get_current_task(journey) or {}
        deadline = int(task.get("deadline_day") or 0)
        completed = set(journey.get("tasks_completed", []) or [])
    except Exception:
        return neutral
    if not deadline or task.get("id") in completed:
        return neutral
    over = current_day - deadline
    late_msg = "This task was planned for Day %d. Pick it up today. Nothing is lost." % deadline
    if operator.ge(over, 3):
        return {"status": "behind", "message": late_msg, "color": "neutral"}
    if operator.gt(over, 0):
        return {"status": "on_track", "message": late_msg, "color": "neutral"}
    ahead = False
    try:
        for phase in JOURNEY_MAP.values():
            for t in phase.get("tasks", []):
                if t.get("id") in completed and operator.gt(int(t.get("deadline_day") or 0), current_day):
                    ahead = True
    except Exception:
        ahead = False
    left = deadline - current_day
    if left == 0:
        msg = "Your current task is planned for Day %d. That's today." % deadline
    else:
        msg = "Your current task is planned for Day %d. You have %d day%s." % (deadline, left, "" if left == 1 else "s")
    if ahead:
        return {"status": "ahead", "message": msg, "color": "green"}
    return {"status": "on_track", "message": msg, "color": "blue"}"""


def fail(msg):
    print("ABORTED - nothing was written.")
    print("Reason: " + msg)
    sys.exit(1)


def main():
    check_only = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = Path(args[0]) if args else Path("/root/e5-ai-coach/main.py")
    backup = target.with_name(target.name + ".bak-brick3_1")
    if not target.is_file():
        fail("file not found: " + str(target))
    for bad in (chr(60), chr(62), chr(38)):
        if bad in NEW_FN:
            fail("replacement contains a forbidden character (copy damage?)")
    src = target.read_text(encoding="utf-8")
    if MARKER in src:
        fail("Brick 3.1 backend marker found - this file is already patched.")
    if NEED not in src:
        fail("Brick 1B is not applied to this main.py. Apply patch_brick1b.py first.")
    if src.count(START) != 1:
        fail("calculate_trajectory definition found " + str(src.count(START)) + " times (expected 1)")
    s0 = src.find(START)
    e0 = src.find(END, s0)
    if e0 == -1:
        fail("could not find the end of calculate_trajectory")
    old = src[s0:e0]
    if OLD_SIGN not in old:
        fail("calculate_trajectory does not look like the original version")
    print("  [OK] calculate_trajectory found (" + str(old.count(chr(10)) + 1) + " lines)")
    if check_only:
        print("CHECK PASSED - nothing written.")
        return
    out = src[:s0] + NEW_FN + src[e0:]
    tmp = target.with_name(target.name + ".tmp-brick3_1.py")
    tmp.write_text(out, encoding="utf-8")
    try:
        py_compile.compile(str(tmp), doraise=True)
    except Exception as e:
        tmp.unlink()
        fail("patched file does not compile: " + str(e))
    shutil.copy2(target, backup)
    os.replace(tmp, target)
    print("PATCHED: " + str(target))
    print("Backup:  " + str(backup))
    print("Rollback: cp " + str(backup) + " " + str(target) + "   then rebuild the container")


main()
