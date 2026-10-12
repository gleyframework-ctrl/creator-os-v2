#!/usr/bin/env python3
"""
patch_brickF3b.py - Brick F.3b: no framework names in the Content drawer pipeline
Target: agentic_core.py only

What it does (14 anchors, each expected once)
  B1   _f3b_plain_rule(): reads _f3_plain_rule from the already-loaded main module
       (sys.modules main or __main__, never imports it). Fallback sentence if absent.
  B2   Constitution rule 1 becomes the plain-words rule.
  B3   execute() (unused): no framework names, plain rule instead of cite by name.
  B4   critique_and_fix() (unused): framework names removed from the critic input.
  B5   Executor intro grounds answers in COACH NOTES (use the ideas, never the names).
  B6   Executor no longer gets the selector names ("Use these frameworks").
  B7   "Cite each framework by name" becomes the plain rule.
  B8   Notes label becomes COACH NOTES (use the ideas, never the names).
  B9   Critic violation list: naming a framework is now the violation.
  B10  Critic gets the plain rule with the banned list.
  B11  Critic no longer gets "Frameworks to cite".
  B12  Reply sends frameworks [] (names stay on the server).
  B13  Wasted diagnose() call removed (select_by_keywords routes). One AI call saved.
  B14  Provider error is printed on the server, the user gets a clean message.

Safety
  - Needs BRICK F.3 in main.py (same folder). Refuses a second run (BRICK F.3b in agentic_core.py).
  - Every anchor is counted before anything is written.
  - Offline run of agentic_pipeline with stubs: no selector names in any prompt, plain rule
    from main in executor and critic, 2 AI calls not 3, frameworks [], clean error. Fallback test.
  - py_compile. Backup agentic_core.py.bak-brickF3b (never overwritten). Atomic write. CRLF safe.

Usage
  python3 patch_brickF3b.py --dry-run
  python3 patch_brickF3b.py
  python3 patch_brickF3b.py --dir /root/e5-ai-coach

Rollback
  cp agentic_core.py.bak-brickF3b agentic_core.py   then restart FastAPI
"""
import argparse
import os
import py_compile
import shutil
import sys
import tempfile
import types
import io
import contextlib

MARKER = "BRICK F.3b"
PREREQ = "BRICK F.3"
TOKENS = ("@LT@", "@GT@", "@AMP@")
FAKE_RULE = "FAKE-PLAIN-RULE-FROM-MAIN"

ANCHORS = [
    (
        'B1 helper before _call',
        'def _call(system, user, max_tokens=2000, temperature=0.5):\n',
        '# ===== BRICK F.3b: plain words in the Content drawer pipeline (same banned list as main.py BRICK F.3) =====\n_F3B_FALLBACK = "Plain everyday words only. Never name a framework, method, book or author."\n\n\ndef _f3b_plain_rule():\n    # main.py imports this module, so main is already loaded: read its rule, never import it again.\n    import sys\n    for name in ("main", "__main__"):\n        fn = getattr(sys.modules.get(name), "_f3_plain_rule", None)\n        if callable(fn):\n            try:\n                return str(fn())\n            except Exception:\n                break\n    return _F3B_FALLBACK\n# ===== end BRICK F.3b =====\n\n\ndef _call(system, user, max_tokens=2000, temperature=0.5):\n',
        1,
    ),
    (
        'B2 constitution rule 1',
        '    "Must cite at least 1 specific framework by name",',
        '    "Must use plain everyday words and never name a framework, method, book or author",',
        1,
    ),
    (
        'B3 execute() system',
        "You MUST use these frameworks: {', '.join(frameworks)}. Business DNA: {business_dna}. Cite each framework by name. ",
        'Business DNA: {business_dna}. {_f3b_plain_rule()} ',
        1,
    ),
    (
        'B4 critique_and_fix() names',
        "\\nFrameworks: {', '.join(frameworks)}",
        '',
        1,
    ),
    (
        'B5 executor intro',
        '        "You are an elite business coach. You MUST ground every answer in the RELEVANT FRAMEWORK CONTENT below. "',
        '        "You are an elite business coach. Ground every answer in the COACH NOTES below (use the ideas, never the names). "',
        1,
    ),
    (
        'B6 executor names line',
        '        "Use these frameworks: " + fw_list + ". "\n',
        '',
        1,
    ),
    (
        'B7 executor cite rule',
        '        "Cite each framework by name. Be specific with numbers. Every action under 20 minutes. "',
        '        + _f3b_plain_rule() + " Be specific with numbers. Every action under 20 minutes. "',
        1,
    ),
    (
        'B8 executor notes label',
        '        "=== RELEVANT FRAMEWORK CONTENT ===\\n" + knowledge_ctx',
        '        "=== COACH NOTES (use the ideas, never the names) ===\\n" + knowledge_ctx',
        1,
    ),
    (
        'B9 critic violation list',
        '(missing framework citation, generic phrases, no specific action, no next step)',
        '(a framework, method, book or author named, generic phrases, no specific action, no next step)',
        1,
    ),
    (
        'B10 critic gets plain rule',
        '        "RULES:\\n" + rules_list',
        '        "RULES:\\n" + rules_list + "\\n- " + _f3b_plain_rule()',
        1,
    ),
    (
        'B11 critic names input',
        '"\\nFrameworks to cite: " + fw_list + ',
        '',
        1,
    ),
    (
        'B12 names stay on server',
        '        "frameworks": frameworks,',
        '        "frameworks": [],  # BRICK F.3b: names stay on the server',
        1,
    ),
    (
        'B13 drop wasted diagnose()',
        '    diagnosis = diagnose(user_prompt)\n    if not diagnosis or diagnosis.startswith("__ERROR__"):\n        diagnosis = "STAGE=convert | CATEGORY=dm | BOTTLENECK=unknown"\n',
        '    # BRICK F.3b: diagnose() removed: select_by_keywords() handles\n    # routing. Saves one AI call per Content drawer request.\n    diagnosis = "STAGE=convert | CATEGORY=dm | BOTTLENECK=unknown"\n',
        1,
    ),
    (
        'B14 no raw error to user',
        '        return {"ok": False, "error": draft}\n',
        '        print("[AGENT] ERROR: " + str(draft)[:500], flush=True)\n        return {"ok": False, "error": "The AI could not answer right now. Please try again."}\n',
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
    for name, old, new, expected in ANCHORS:
        old, new = decode(old), decode(new)
        n = text.count(old)
        print("  %-30s found %d (expected %d)" % (name, n, expected))
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


def load_module(out):
    saved = {k: sys.modules.get(k) for k in ("openai", "knowledge_loader", "main")}
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda *a, **k: None
    fake_kl = types.ModuleType("knowledge_loader")
    fake_kl.get_context = lambda *a, **k: "NOTES-TEXT"
    sys.modules["openai"] = fake_openai
    sys.modules["knowledge_loader"] = fake_kl
    sys.modules.pop("main", None)
    mod = types.ModuleType("agentic_core_f3b_test")
    exec(compile(out, "agentic_core.py", "exec"), mod.__dict__)
    return mod, saved


def restore(saved):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def check_pipeline(out):
    mod, saved = load_module(out)
    try:
        ns = mod.__dict__
        names = set()
        for stage in ns["FRAMEWORK_GRAPH"].values():
            for lst in stage.values():
                names.update(lst)
        prompts = ["How do I get more DM replies?", "Help me price my offer", "Ideas for a reel hook",
                   "Grow my community members", "Plan my webinar launch", "Fix my funnel conversion",
                   "Who is my target avatar", "Hello"]
        for p in prompts:
            names.update(ns["select_by_keywords"](p)[2])
        if ns["_f3b_plain_rule"]() != ns["_F3B_FALLBACK"]:
            fail("fallback: rule should be the fallback sentence when main is not loaded")
        fake_main = types.ModuleType("main")
        fake_main._f3_plain_rule = lambda: FAKE_RULE
        sys.modules["main"] = fake_main
        for p in prompts:
            calls = []

            def stub(system, user, max_tokens=2000, temperature=0.5):
                calls.append((system, user))
                return "DRAFT-TEXT" if len(calls) == 1 else "FINAL-TEXT"
            ns["_call"] = stub
            with contextlib.redirect_stdout(io.StringIO()):
                r = ns["agentic_pipeline"](p, "dna here")
            if len(calls) != 2:
                fail("pipeline: expected 2 AI calls, got " + str(len(calls)))
            for system, user in calls:
                blob = system + "\n" + user.replace("DRAFT-TEXT", "")
                hit = [n for n in names if n in blob]
                if hit:
                    fail("pipeline: selector name in a prompt: " + str(hit[:3]))
                if FAKE_RULE not in system:
                    fail("pipeline: plain rule from main missing in a system prompt")
            ex, cr = calls[0][0], calls[1][0]
            for w in ("COACH NOTES (use the ideas, never the names)", "End with a clear next step.",
                      "RULES (violating any = failure):", "NOTES-TEXT", "Business DNA: dna here"):
                if w not in ex:
                    fail("pipeline: executor prompt missing: " + w)
            if "a framework, method, book or author named" not in cr or "Must use plain everyday words" not in cr:
                fail("pipeline: critic prompt not updated")
            if r.get("ok") is not True or r.get("text") != "FINAL-TEXT" or r.get("frameworks") != []:
                fail("pipeline: wrong reply " + str(r))
            if not r.get("stage") or not r.get("category"):
                fail("pipeline: stage or category lost")
        ns["_call"] = lambda *a, **k: "__ERROR__secret provider detail"
        with contextlib.redirect_stdout(io.StringIO()):
            r = ns["agentic_pipeline"]("How do I get more DM replies?", "dna")
        if r != {"ok": False, "error": "The AI could not answer right now. Please try again."}:
            fail("pipeline: error reply not clean " + str(r))
        def ex_stub(system, user, max_tokens=2000, temperature=0.5):
            ex_stub.s = system
            return "x"
        ns["_call"] = ex_stub
        ns["execute"]("q", ["ECAFI", "S.I.P.E."], "dna")
        if "ECAFI" in ex_stub.s or FAKE_RULE not in ex_stub.s:
            fail("execute(): names still in prompt or rule missing")
        def cr_stub(system, user, max_tokens=2000, temperature=0.5):
            cr_stub.u = user
            return "x"
        ns["_call"] = cr_stub
        ns["critique_and_fix"]("q", ["ECAFI"], "dna", "draft")
        if "ECAFI" in cr_stub.u:
            fail("critique_and_fix(): names still in critic input")
    finally:
        restore(saved)
    print("  fallback: plain sentence when main is not loaded")
    print("  pipeline (8 prompts): 2 AI calls, no selector names, plain rule from main, frameworks [], stage/category kept")
    print("  error path: clean message, no provider text; execute() and critique_and_fix() clean")


def main():
    ap = argparse.ArgumentParser(description="Brick F.3b: plain words in agentic_core.py")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = os.path.join(args.dir, "agentic_core.py")
    main_path = os.path.join(args.dir, "main.py")
    for p in (path, main_path):
        if not os.path.isfile(p):
            fail(os.path.basename(p) + " not found in " + os.path.abspath(args.dir))
    if PREREQ not in open(main_path, encoding="utf-8").read():
        fail("BRICK F.3 not found in main.py. Apply Brick F.3 first.")
    raw = open(path, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if MARKER in text:
        fail("Brick F.3b is already applied to agentic_core.py (second run refused)")
    print("agentic_core.py: " + path + (" (CRLF)" if crlf else ""))
    print("Anchors:")
    out = apply_anchors(text)
    print("Checks:")
    if MARKER not in out:
        fail("marker missing after patch")
    for t in TOKENS:
        if t in out:
            fail("token " + t + " left in output")
    if [c for c in set(out) - set(text) if not c.isascii()]:
        fail("non-ASCII text added")
    low = out.lower()
    for w in ("cite", "use these frameworks", "frameworks to cite", "relevant framework content",
              "missing framework citation", "= diagnose(user_prompt)", '"error": draft'):
        if w in low:
            fail("old text still present: " + w)
    print("  old cite / names / raw-error text gone")
    check_pipeline(out)
    final = out.replace("\n", "\r\n") if crlf else out
    fd, tmp = tempfile.mkstemp(prefix=".brickF3b-", suffix=".py", dir=os.path.dirname(os.path.abspath(path)))
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
        bak = path + ".bak-brickF3b"
        if os.path.exists(bak):
            print("Backup already exists, kept as is: " + bak)
        else:
            shutil.copy2(path, bak)
            print("Backup: " + bak)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
        tmp = None
        print("DONE: Brick F.3b applied. Restart FastAPI.")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
