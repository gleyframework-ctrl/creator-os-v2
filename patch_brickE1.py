#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_brickE1.py  --  Brick E1, one patch for two files

Part A  main.py (server freeze fix)
    The two synchronous AI calls inside async routes now run in the threadpool,
    so one slow AI call no longer freezes every other user (single uvicorn worker):
      - analyze_funnel : call_llm(...)          -- line ~995
      - ai_agentic     : agentic_pipeline(...)  -- line ~2079
    Same prompts, same arguments, same return values, same error handling.

Part B  chat_test.html (E1 progress one-liner)
    journeySummary() now shows todayProgress() ("Day X of 90 - N of 12 tasks" + bar)
    and the streak only when it is above 0. Removed: the stats grid, the XP box,
    the Health score box, the % bar and the "% of tasks completed" hint.
    Pace line, current task, Start/Daily standup buttons are unchanged.

Usage (in /root/e5-ai-coach/):
    python3 patch_brickE1.py --check    # dry run: every check + compile, writes nothing
    python3 patch_brickE1.py            # apply
Options:
    --dir PATH          folder holding main.py and chat_test.html (default: current folder)
    --skip-js-check     only if node is not installed (not recommended)

Rollback:
    cp main.py.bak-brickE1 main.py
    cp chat_test.html.bak-brickE1 chat_test.html
"""
import os, sys, shutil, subprocess, tempfile, py_compile, operator as op

LT, GT, AMP = chr(60), chr(62), chr(38)


def u(s):
    return s.replace('@LT@', LT).replace('@GT@', GT).replace('@AMP@', AMP)


MARK = 'BRICK E1'
NEED_MAIN = 'BRICK 4'
NEED_HTML = 'BRICK 5'
BAK = '.bak-brickE1'

MAIN_EDITS = [
    ('analyze_funnel: load threadpool helper',
     '@app.post("/api/analyze-funnel")\nasync def analyze_funnel(request: Request):',
     '# ===== BRICK E1A: server freeze fix. Sync AI calls inside async routes run in the threadpool. =====\nfrom starlette.concurrency import run_in_threadpool as _e1_pool\n\n@app.post("/api/analyze-funnel")\nasync def analyze_funnel(request: Request):'),
    ('analyze_funnel: call_llm runs in threadpool',
     '        analysis = call_llm([{"role": "system", "content": "You are a world-class funnel hacker. Cite frameworks (CVJ, STORM, Value Equation). Score each section /100. Give specific fixes with time estimates. No generic advice."}, {"role": "user", "content": prompt}], temperature=0.4, max_tokens=3000)',
     '        analysis = await _e1_pool(call_llm, [{"role": "system", "content": "You are a world-class funnel hacker. Cite frameworks (CVJ, STORM, Value Equation). Score each section /100. Give specific fixes with time estimates. No generic advice."}, {"role": "user", "content": prompt}], temperature=0.4, max_tokens=3000)  # BRICK E1A'),
    ('ai_agentic: agentic_pipeline runs in threadpool',
     '        return agentic_pipeline(req.prompt, req.dna)',
     '        return await _e1_pool(agentic_pipeline, req.prompt, req.dna)  # BRICK E1A'),
]

HTML_EDITS = [
    ('journeySummary: drop grid, XP and Health variables',
     ' const ps=phases(),total=ps.reduce((a,[k,p])=@GT@a+(p.tasks||[]).length,0)||12,done=Math.max(0,num(j.tasks_completed_count)),progress=clamp(done/total*100,0,100),health=j.health_score??j.health?.score;',
     ' // ===== BRICK E1: progress one-liner. todayProgress() plus streak only above 0. No stats grid, no XP, no Health score, no % bar. =====\n const streak=Math.max(0,Math.floor(num(j.streak)));'),
    ('journeySummary: grid + % bar + hint replaced by todayProgress()',
     ' @LT@div class="stats journey-stats"@GT@${[[\'Day\',int(j.current_day||1)+\'/90\'],[\'Tasks\',int(done)+\'/\'+total],...(num(j.xp)?[[\'XP\',int(j.xp)]]:[]),[\'Streak\',int(j.streak)+\' days\'],[\'Health score\',health==null?\'@LT@span class="hint"@GT@\'+esc(tx(\'We’ll build this as you go\'))+\'@LT@/span@GT@\':esc(health)]].map(x=@GT@`@LT@div@GT@@LT@span class="hint"@GT@${x[0]}@LT@/span@GT@@LT@div class="metric"@GT@${x[1]}@LT@/div@GT@@LT@/div@GT@`).join(\'\')}@LT@/div@GT@\n @LT@progress class="wide-progress" value="${progress}" max="100" aria-label="Journey progress"@GT@${Math.round(progress)}%@LT@/progress@GT@@LT@p class="hint"@GT@${Math.round(progress)}% of tasks completed@LT@/p@GT@',
     ' ${todayProgress()}${streak?\'@LT@p class="hint" style="margin:-12px 0 16px"@GT@\'+esc(S.ui.lang===\'ar\'?\'سلسلة الأيام: \'+int(streak):int(streak)+\'-day streak\')+\'@LT@/p@GT@\':\'\'}'),
]


def fail(msg):
    print('REFUSED: ' + msg)
    sys.exit(1)


def read(p):
    with open(p, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def apply_edits(text, edits, fname):
    for label, old, new in edits:
        o, n = u(old), u(new)
        c = text.count(o)
        if op.ne(c, 1):
            fail(fname + ': anchor for "' + label + '" found ' + str(c) +
                 ' times (expected exactly 1). This file differs from the version the patch was tested on.')
        text = text.replace(o, n, 1)
        print('  ok  ' + fname + ': ' + label)
    return text


def js_of(html):
    open_tag = u('@LT@script id="creator-os-app"@GT@')
    close_tag = u('@LT@/script@GT@')
    a = html.find(open_tag)
    if op.lt(a, 0):
        fail('chat_test.html: app script tag not found')
    a += len(open_tag)
    b = html.find(close_tag, a)
    if op.lt(b, 0):
        fail('chat_test.html: closing script tag not found')
    return html[a:b]


def node_check(js):
    node = shutil.which('node')
    if not node:
        fail('node not found. Install node, or rerun with --skip-js-check (not recommended).')
    fd, p = tempfile.mkstemp(suffix='.js')
    os.close(fd)
    try:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(js)
        r = subprocess.run([node, '--check', p], capture_output=True, text=True)
        return r.returncode, (r.stderr or r.stdout).strip()
    finally:
        os.remove(p)


def py_check(src):
    fd, p = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    try:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(src)
        py_compile.compile(p, cfile=p + 'c', doraise=True)
    except py_compile.PyCompileError as e:
        fail('main.py would not compile after the patch: ' + str(e))
    finally:
        for x in (p, p + 'c'):
            if os.path.exists(x):
                os.remove(x)


def backup(path):
    b = path + BAK
    if os.path.exists(b):
        if read_bytes(b) == read_bytes(path):
            print('  ok  backup ' + b + ' already exists and matches, reused')
            return b
        fail(b + ' already exists and differs from the current file. Move it away first.')
    shutil.copy2(path, b)
    print('  ok  backup ' + b)
    return b


def write(path, text):
    tmp = path + '.tmp-brickE1'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    shutil.copymode(path, tmp)
    os.replace(tmp, path)


def main():
    args = sys.argv[1:]
    known = ('--check', '--skip-js-check', '--dir')
    for a in args:
        if a.startswith('--') and a not in known:
            fail('unknown option ' + a)
    check_only = '--check' in args
    skip_js = '--skip-js-check' in args
    folder = '.'
    if '--dir' in args:
        i = args.index('--dir')
        if op.ge(i + 1, len(args)):
            fail('--dir needs a path')
        folder = args[i + 1]
    mp = os.path.join(folder, 'main.py')
    hp = os.path.join(folder, 'chat_test.html')
    for p in (mp, hp):
        if not os.path.isfile(p):
            fail(p + ' not found. Run this in /root/e5-ai-coach/ or pass --dir.')
    main_src, html_src = read(mp), read(hp)
    print('Brick E1 patch' + (' (check only, nothing will be written)' if check_only else ''))

    for p, s in ((mp, main_src), (hp, html_src)):
        if MARK in s:
            fail(MARK + ' marker already in ' + p + '. Brick E1 is applied (or half applied). '
                 'To redo it, restore both .bak-brickE1 files first.')
    if NEED_MAIN not in main_src:
        fail('BRICK 4 marker not found in main.py. Apply Brick 4 first.')
    if NEED_HTML not in html_src:
        fail('BRICK 5 marker not found in chat_test.html. Apply Brick 5 first.')
    print('  ok  prerequisites: BRICK 4 in main.py, BRICK 5 in chat_test.html')

    new_main = apply_edits(main_src, MAIN_EDITS, 'main.py')
    new_html = apply_edits(html_src, HTML_EDITS, 'chat_test.html')
    if MARK not in new_main or MARK not in new_html:
        fail('internal error: marker missing after edits')

    py_check(new_main)
    print('  ok  py_compile main.py (patched)')
    if skip_js:
        print('  WARN JS check skipped (--skip-js-check)')
    else:
        rc, err = node_check(js_of(html_src))
        if op.ne(rc, 0):
            fail('node --check fails on the ORIGINAL chat_test.html, so the checker cannot be trusted: ' + err)
        rc, err = node_check(js_of(new_html))
        if op.ne(rc, 0):
            fail('patched chat_test.html JS fails node --check: ' + err)
        print('  ok  node --check chat_test.html (patched)')

    if check_only:
        print('CHECK OK. Nothing written. Run again without --check to apply.')
        return

    backup(mp)
    backup(hp)
    write(mp, new_main)
    try:
        write(hp, new_html)
    except Exception:
        shutil.copy2(mp + BAK, mp)
        print('ERROR writing chat_test.html. main.py was restored from its backup.')
        raise
    if MARK not in read(mp) or MARK not in read(hp):
        fail('verification after write failed. Restore both .bak-brickE1 files.')
    print('DONE. Brick E1 applied to main.py and chat_test.html.')
    print('Next: docker compose down; docker compose up -d --build; purge Cloudflare cache for /app.')


main()
