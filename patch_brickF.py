#!/usr/bin/env python3
"""
BRICK F: EMBEDDED COACH IN TRY AGAIN
====================================

What it does
------------
When a standup fails and the user clicks "Try again"
(button[data-act="standup-retry"] in the result modal footer), the standup
modal reopens with the saved text exactly as before, and a small Coach panel
appears under the character counter:

  1. A coach bubble, built in the browser from E3.last.missing_items[0]
     (the biggest gap), or E3.last.hint if the list is empty. No AI call.
  2. One concrete suggestion, streamed from the existing /api/chat/stream
     (SSE) with mode "standup_fix", with a Copy button. The textarea is never
     written to: the user pastes and edits.
  3. Exactly ONE follow-up question (one input, one Send button). After that
     reply the input locks: "Now edit your text above and submit."
  4. Plain language only. The server uses a short plain prompt for mode
     standup_fix. The browser also checks the finished reply against a copy of
     the E3 jargon list (same rule: CAPS case-sensitive, NAMES case-insensitive,
     whole words) and shows E3.last.hint instead if a term is found.
  5. E3.last is only read, never written. Closing the modal mid-reply aborts
     the stream and saves nothing.

Files and anchors (name, old, new, expected_count)
--------------------------------------------------
chat_test.html
  H1  ACT['standup-retry']=()=@GT@standupModal();                    x1
main.py
  M1  @app.post("/api/chat/stream")                                     x1
  M2  system_prompt = _b5_system_prompt(...) line in both chat routes   x2
  M3  _E3_JARGON_CAPS = [   (sync comment only, list unchanged)         x1
No new endpoint. StandupRequest, ChatRequest, the grader, scoring and the
E3.1 helpers are not changed.

Safety
------
  * Refuses unless BRICK E3.1 is in both files.
  * Refuses a second run (BRICK F in either file).
  * Every anchor must match exactly expected_count times, or nothing is written.
  * Tokens in this file: @LT@ = less-than, @GT@ = greater-than, @AMP@ = ampersand.
    This file is ASCII only, and so is every inserted line.
  * Before writing: main.py is compiled; the app script in chat_test.html is
    checked with node --check (skipped with a warning if node is missing).
  * Backups: main.py.bak-brickF and chat_test.html.bak-brickF (never overwritten).
  * Atomic writes (temp file + fsync + os.replace). If the second write fails,
    main.py is restored from its backup.

Usage
-----
    cd /root/e5-ai-coach
    python3 patch_brickF.py --dry-run
    python3 patch_brickF.py
    python3 patch_brickF.py --dir /root/e5-ai-coach
Then restart the FastAPI server and hard-refresh the browser.

Rollback
--------
    cp main.py.bak-brickF main.py
    cp chat_test.html.bak-brickF chat_test.html
"""
# BRICK F: EMBEDDED COACH IN TRY AGAIN


import os
import re
import sys
import shutil
import tempfile
import subprocess

MARKER = "BRICK F"
PREREQ_MARKERS = ["BRICK E3.1"]
BACKUP_SUFFIX = ".bak-brickF"
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
        'main: Brick F prompt helper before the stream route',
        '@app.post("/api/chat/stream")',
        r'''# ===== BRICK F: EMBEDDED COACH IN TRY AGAIN. Plain prompt for chat mode "standup_fix". =====
# Used only when the request says mode == "standup_fix" (sent by the Try again coach panel).
# Any other mode, or any error, returns the prompt unchanged. Grader and scoring are not touched.
BF_MODE = "standup_fix"


def _bf_system_prompt(req, current_task, default_prompt):
    try:
        if str(getattr(req, "mode", "") or "") != BF_MODE:
            return default_prompt
        task = current_task if isinstance(current_task, dict) else {}
        N = chr(10)
        rubric = _e3_rubric(task)
        parts = N.join("- " + str(d) for d in task.get("deliverables", [])) or "- (no list given)"
        needs = []
        if rubric.get("link"):
            needs.append("a link to their work")
        if rubric.get("metrics"):
            needs.append("their real numbers")
        lines = [
            "You help someone fix their daily standup before they submit it again. Their last try did not pass yet.",
            "",
            "TASK: " + str(task.get("name", "")),
            "THE PARTS OF THIS TASK:", parts,
            "THIS TASK ALSO NEEDS: " + (", ".join(needs) if needs else "nothing else"),
            "",
            "The user message has their current text, their score, the reason, a hint and what is still missing.",
            "",
            "Rules:",
            "- Plain everyday words, like a kind friend. No jargon, no acronyms, no framework names, no author or book names.",
            "- Never lecture. No lists of tips, no headings, no markdown.",
            "- 2 to 4 short sentences in total.",
            "- First reply: give ONE concrete suggestion for the biggest missing item: one or two sentences they could add to their own text, in their voice, inside double quotes. Use only facts from their text. Where a fact is missing, leave a blank like [your number].",
            "- Follow-up: answer their question directly in 1 to 3 sentences, then stop.",
            "- Never rewrite their whole text. Never invent results, numbers or links.",
            "- Write in the same language as their text.",
        ]
        return N.join(lines)
    except Exception:
        return default_prompt
# ===== end BRICK F helper =====


@app.post("/api/chat/stream")''',
        1,
    ),
    (
        'main: prompt switch in /api/chat and /api/chat/stream',
        '    system_prompt = _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context, standups_text, wins_full_text, system_prompt)',
        r'''    system_prompt = _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context, standups_text, wins_full_text, system_prompt)
    system_prompt = _bf_system_prompt(req, current_task, system_prompt)  # BRICK F''',
        2,
    ),
    (
        'main: sync comment above the E3 jargon list',
        '_E3_JARGON_CAPS = [',
        r'''# Keep in sync with chat_test.html BF_JARGON_CAPS / BF_JARGON_NAMES (BRICK F)
_E3_JARGON_CAPS = [''',
        1,
    ),
]

HTML_ANCHORS = [
    (
        'html: Try again hook + Brick F coach block',
        "ACT['standup-retry']=()=@GT@standupModal();",
        r'''// ===== BRICK F: EMBEDDED COACH IN TRY AGAIN. Reads E3.last (never writes it). One suggestion, one follow-up. Reuses /api/chat/stream with mode standup_fix. =====
// Keep in sync with main.py E3 jargon list (_E3_JARGON_CAPS / _E3_JARGON_NAMES). Same rule: CAPS case-sensitive, NAMES case-insensitive, whole words.
const BF_JARGON_CAPS=["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S"];
const BF_JARGON_NAMES=["Hormozi", "Kallaway", "Cattoni", "Tutton", "Belcher", "Rohan", "Value Equation", "Pain Stack", "Tiny Yeses", "DM Doctor", "Offer Architect", "Community OS", "Content Engine", "Dream Customer", "Dream Follower", "Hook Mastery", "Anti-viral", "Launch Planner", "21-day launch map", "Customer Value Journey"];
const BF_MODE='standup_fix';
const BF={ctl:null,busy:false,asked:false,history:[]};
function bfAlt(list){return list.map(w=@GT@String(w).replace(/[.*+?^${}()|[\]\\]/g,'\\$@AMP@')).join('|');}
const BF_CAPS_RE=new RegExp('\\b('+bfAlt(BF_JARGON_CAPS)+')\\b');
const BF_NAMES_RE=new RegExp('\\b('+bfAlt(BF_JARGON_NAMES)+')\\b','i');
function bfHasJargon(s){s=String(s||'');return BF_CAPS_RE.test(s)||BF_NAMES_RE.test(s);}
function bfLast(){const l=E3.last;return l@AMP@@AMP@typeof l==='object'?l:null;}
function bfLabel(x){return e3Plain(x@AMP@@AMP@typeof x==='object'?x.label:x).replace(/[.\s]+$/,'');}
function bfItems(last){return (Array.isArray(last.missing_items)?last.missing_items:[]).map(bfLabel).filter(Boolean);}
function bfFallback(last){return e3Plain(last@AMP@@AMP@last.hint)||'Add the missing part in a few clear lines, then submit again.';}
function bfOpening(last){const items=bfItems(last);if(items.length)return 'The biggest thing missing: '+items[0]+'.';return bfFallback(last);}
function bfAbort(){if(BF.ctl){try{BF.ctl.abort('closed');}catch(e){}BF.ctl=null;}}
function bfBubble(text,who){const log=$('#bfLog');if(!log)return null;const p=document.createElement('p');p.className='mt-s bf-msg bf-'+who;const b=document.createElement('b');b.textContent=who==='user'?'You: ':'Coach: ';const s=document.createElement('span');s.className='bf-text';s.textContent=text;p.append(b,s);log.append(p);return p;}
function bfSetText(p,text){const s=p@AMP@@AMP@p.querySelector('.bf-text');if(s)s.textContent=text;}
function bfLock(locked,note){const i=$('#bfInput'),b=$('#bfSend'),n=$('#bfNote');if(i)i.disabled=locked;if(b)b.disabled=locked;if(n)n.textContent=note||'';}
function bfQuote(text){const m=String(text).match(/["\u201C\u00AB]([^"\u201D\u00BB]{8,})["\u201D\u00BB]/);return m?m[1].trim():String(text).trim();}
async function bfCopy(text){
 try{if(navigator.clipboard@AMP@@AMP@window.isSecureContext){await navigator.clipboard.writeText(text);}else{const t=document.createElement('textarea');t.value=text;t.setAttribute('readonly','');t.style.position='fixed';t.style.opacity='0';document.body.append(t);t.select();document.execCommand('copy');t.remove();}toast('Copied. Paste it into your text and make it yours.');}
 catch(e){toast('Copy did not work. Select the text and copy it by hand.');}
}
function bfAddCopy(p,text){if(!p)return;const b=document.createElement('button');b.type='button';b.className='btn btn-sm mt-s';b.textContent='Copy';b.addEventListener('click',()=@GT@bfCopy(bfQuote(text)));p.append(document.createElement('br'),b);}
async function bfStream(body,ctl,msg){
 let text='';
 const r=await fetch('/api/chat/stream',{method:'POST',credentials:'same-origin',headers:jsonHeaders(),body:JSON.stringify(body),signal:ctl.signal});
 if(!r.ok||!r.body){if([404,405,501].includes(r.status)){const d=await postJSON('/api/chat',body,120000,ctl.signal);return String(d.reply||d.text||'');}throw new Error(await responseError(r));}
 if(!String(r.headers.get('content-type')).includes('text/event-stream')){const d=await r.json();return String(d.reply||d.text||'');}
 const reader=r.body.getReader(),dec=new TextDecoder();let buf='',done=false;
 const frame=f=@GT@{const lines=f.split('\n').filter(l=@GT@l.startsWith('data:')).map(l=@GT@l.slice(5).trimStart());if(!lines.length)return;const payload=lines.join('\n').trim();if(payload==='[DONE]'){done=true;return;}let d;try{d=JSON.parse(payload);}catch(e){return;}if(d.error)throw new Error(String(d.error));const t=d.token??d.content??d.delta?.content;if(typeof t==='string')text+=t;};
 try{
  while(!done){const x=await reader.read();buf=(buf+dec.decode(x.value||new Uint8Array(),{stream:!x.done})).replace(/\r\n/g,'\n');let cut;while((cut=buf.indexOf('\n\n'))@GT@=0){frame(buf.slice(0,cut));buf=buf.slice(cut+2);}if(!document.body.contains(msg)){ctl.abort('closed');break;}bfSetText(msg,text||'...');if(x.done){if(buf.trim())frame(buf);break;}}
 }finally{await reader.cancel().catch(()=@GT@{});}
 return text;
}
async function bfAsk(question,first){
 if(BF.busy)return;const last=bfLast(),box=$('#standupText');if(!last||!box)return;
 BF.busy=true;bfLock(true,first?'':'Thinking...');
 const msg=bfBubble('...','coach');const N='\n';
 const message='MY CURRENT TEXT:'+N+String(box.value||'').slice(0,8000)+N+N+'SCORE: '+(last.score==null?'?':String(last.score))+'/10'+N+'REASON: '+e3Plain(last.reason)+N+'HINT: '+e3Plain(last.hint)+N+'STILL MISSING: '+(bfItems(last).join('; ')||'nothing listed')+N+N+(first?'':'MY QUESTION: ')+question;
 const body={message,mode:BF_MODE,member_id:memberId(),history:BF.history.slice(-4),beginner:guidedOn()};
 const ctl=new AbortController();BF.ctl=ctl;
 const timer=setTimeout(()=@GT@ctl.abort('timeout'),120000);
 const watch=setInterval(()=@GT@{if(!document.body.contains(msg))ctl.abort('closed');},500);
 let text='',failed=false;
 try{text=String(await bfStream(body,ctl,msg)||'').trim();aiText(text);}
 catch(e){failed=true;}
 finally{clearTimeout(timer);clearInterval(watch);if(BF.ctl===ctl)BF.ctl=null;BF.busy=false;}
 if(!msg||!document.body.contains(msg))return;
 if(failed||!text){bfSetText(msg,'The coach could not answer right now. Your text is saved: edit it and submit.');}
 else{
  const jargon=bfHasJargon(text);
  if(jargon){console.warn('[BrickF] coach reply contained a jargon term; showing the E3 hint instead.');text=bfFallback(last);}
  bfSetText(msg,text);if(!jargon)bfAddCopy(msg,text);
  BF.history.push({role:'user',content:message},{role:'assistant',content:text});
 }
 if(BF.asked)bfLock(true,'Now edit your text above and submit.');else bfLock(false,'You can ask the coach one question.');
}
function bfFollowUp(){
 if(BF.busy||BF.asked)return;const i=$('#bfInput');const v=String(i@AMP@@AMP@i.value||'').trim();if(!v)return;
 BF.asked=true;i.value='';bfBubble(v,'user');bfAsk(v,false);
}
function bfMount(){
 try{
  const last=bfLast(),box=$('#standupText'),counter=$('#standupCounter');if(!last||!box||!counter)return;
  bfAbort();const old=$('#bfPanel');if(old)old.remove();
  BF.busy=false;BF.asked=false;BF.history=[];
  const p=document.createElement('div');p.id='bfPanel';p.className='callout mt';p.setAttribute('role','region');p.setAttribute('aria-label','Coach help for this retry');
  p.innerHTML='@LT@b@GT@Coach@LT@/b@GT@@LT@div id="bfLog" role="log" aria-live="polite"@GT@@LT@/div@GT@@LT@div class="row mt-s"@GT@@LT@input id="bfInput" type="text" maxlength="1000" dir="auto" autocomplete="off" style="flex:1" placeholder="Ask one question about this task" aria-label="Ask the coach one question"@GT@@LT@button class="btn btn-primary" type="button" id="bfSend"@GT@Send@LT@/button@GT@@LT@/div@GT@@LT@p class="hint mt-s" id="bfNote"@GT@@LT@/p@GT@';
  counter.insertAdjacentElement('afterend',p);
  bfBubble(bfOpening(last),'coach');
  $('#bfSend').addEventListener('click',bfFollowUp);
  $('#bfInput').addEventListener('keydown',e=@GT@{if(e.key==='Enter'@AMP@@AMP@!e.isComposing){e.preventDefault();e.stopPropagation();bfFollowUp();}});
  bfAsk('Give me one concrete suggestion for the biggest missing item.',true);
 }catch(e){console.warn('[BrickF] coach panel could not open',e);}
}
// ===== end BRICK F core =====
ACT['standup-retry']=()=@GT@{standupModal();bfMount();};''',
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
    fd, tmp = tempfile.mkstemp(prefix=".brickF-check-", suffix=".js", dir=folder)
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
    fd, tmp = tempfile.mkstemp(prefix=".brickF-", suffix=".tmp", dir=folder)
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
    print("BRICK F patch -- folder: " + folder)

    for p in (main_path, html_path):
        if not os.path.isfile(p):
            fail("file not found: " + p)
    main_src, html_src = read(main_path), read(html_path)

    # 1. Refuse a second run
    for label, src in ((MAIN_FILE, main_src), (HTML_FILE, html_src)):
        if MARKER in src:
            fail(MARKER + " marker already present in " + label + ". Already applied (or half applied: restore both .bak-brickF files).")

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
    for name, old, new, expected in MAIN_ANCHORS + HTML_ANCHORS:
        if not decode(new).isascii():
            fail("post-check: non-ASCII text in anchor " + name)
    if not open(os.path.abspath(__file__), encoding="utf-8").read().isascii():
        fail("post-check: this patch file is not ASCII")
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

    print("DONE BRICK F applied. Restart the FastAPI server, then hard-refresh the browser.")


if __name__ == "__main__":
    main(sys.argv[1:])
