#!/usr/bin/env python3
"""
BRICK 3.1 (frontend hotfix) - honest Progress screen. Patches chat_test.html only.
  - Pace line from the current task's own deadline_day (neutral colour, never yellow).
    The server trajectory message is no longer shown anywhere.
  - Health score: "We'll build this as you go" until the server sends a real score.
  - XP box hidden until XP is above 0. Streak stays.
  - Progress folded: current phase open, other phases collapsed, framework tags and
    deliverables behind "Details". Start this task visible only on the current task;
    other tasks keep it behind Details. Generate / Refresh / activity move below.
  - "Start with AI Coach" becomes "Start with Coach" (the one primary button).
  - "View journey" hidden on Progress itself (kept on the old Dashboard view).
  - Funnel tile: revenue goal shown only after the user edits it (funnel.goalSet).
  - Top bar: buttons and labels no longer break onto two lines.
Requires Brick 3.

Usage:
  python3 patch_brick3_1_frontend.py --check          dry run, writes nothing
  python3 patch_brick3_1_frontend.py                  patch /root/e5-ai-coach/chat_test.html
  python3 patch_brick3_1_frontend.py /path/file.html  patch another copy

Copy-safety: this file contains NO less-than, greater-than or ampersand characters.
They are written as {LT} and {GT} and rebuilt with chr() at runtime.
Nothing is written unless every anchor is found exactly once.
"""
import os
import shutil
import sys
from pathlib import Path

LT = chr(60)
GT = chr(62)
AMP = chr(38)
MARKER = "BRICK 3.1: Progress fold"
NEED = "BRICK 3: Tools launcher"


def A(s):
    return s.replace("{LT}", LT).replace("{GT}", GT)


CORE_JS = r"""
// ===== BRICK 3.1: Progress fold + honest pace =====
function b31n(x){return Math.round(num(x));}
// Pace from the current task's own deadline. Neutral colour. No line when there is no deadline.
function paceHTML(j){
 try{
  const t=j?j.current_task:null;if(!t)return '';if(t.completed)return '';
  const dl=b31n(t.deadline_day);if(!dl)return '';
  const day=Math.max(1,b31n(j.current_day)||1),left=dl-day;
  let msg='';
  if(left===0)msg='Your current task is planned for Day '+dl+'. That’s today.';
  else if(Math.abs(left)===left)msg='Your current task is planned for Day '+dl+'. You have '+plural(left,'day')+'.';
  else msg='This task was planned for Day '+dl+'. Pick it up today. Nothing is lost.';
  return '{LT}div class="callout"{GT}'+esc(msg)+'{LT}/div{GT}';
 }catch(e){return '';}
}
function progressCurrentPhase(ps){
 const j=S.main.journey||{},cid=String((j.current_task||{}).id||'');let k='';
 ps.forEach(function(e){if(k)return;if(!cid)return;const ts=Array.isArray(e[1].tasks)?e[1].tasks:[];if(ts.some(function(t){return String(t.id)===cid;}))k=e[0];});
 if(!k)ps.forEach(function(e){if(k)return;const ts=Array.isArray(e[1].tasks)?e[1].tasks:[];if(ts.some(function(t){return !t.completed;}))k=e[0];});
 if(!k)if(ps.length)k=ps[0][0];
 return k;
}
function progressTaskHTML(t,isCur){
 const tags=(t.frameworks||[t.framework]).filter(Boolean).map(function(f){return '{LT}span class="tag"{GT}'+esc(f)+'{LT}/span{GT}';}).join(' ');
 const dels=(t.deliverables||[t.deliverable]).filter(Boolean).map(function(d){return '{LT}li{GT}'+esc(d)+'{LT}/li{GT}';}).join('');
 const btn='{LT}button class="btn btn-sm" data-act="start-task" data-id="'+esc(t.id)+'"{GT}'+esc(tx('Start this task'))+' '+ic('arrow')+'{LT}/button{GT}';
 const status=t.completed?tx('Complete'):(isCur?tx('Current task'):(t.deadline_day?'Day '+b31n(t.deadline_day):tx('Ready to start')));
 const why='{LT}p class="muted mt-s"{GT}'+esc(t.why||'This task builds a concrete asset for your customer acquisition system.')+'{LT}/p{GT}';
 let h='{LT}div class="journey-task"{GT}{LT}div class="row between"{GT}{LT}h4{GT}'+(t.completed?ic('check'):ic('clock'))+' '+esc(t.name||'Task')+'{LT}/h4{GT}{LT}span class="tag"{GT}'+esc(status)+'{LT}/span{GT}{LT}/div{GT}';
 if(isCur)h+=why+'{LT}div class="row mt-s"{GT}'+btn+'{LT}/div{GT}';
 h+='{LT}details class="mt-s"{GT}{LT}summary class="hint"{GT}'+esc(tx('Details'))+toolArrow()+'{LT}/summary{GT}'
  +(isCur?'':why)+(tags?'{LT}div class="mt-s"{GT}'+tags+'{LT}/div{GT}':'')+(dels?'{LT}ul{GT}'+dels+'{LT}/ul{GT}':'')
  +((isCur||t.completed)?'':btn)+'{LT}/details{GT}';
 return h+'{LT}/div{GT}';
}
function progressPhaseHTML(k,p,open){
 const ts=Array.isArray(p.tasks)?p.tasks:[],done=ts.filter(function(t){return t.completed;}).length,name=esc(p.name||k);
 const cid=String(((S.main.journey||{}).current_task||{}).id||'');
 const body=ts.map(function(t){return progressTaskHTML(t,open?String(t.id)===cid:false);}).join('');
 if(open)return '{LT}section class="card mt"{GT}{LT}div class="card-h"{GT}{LT}h3{GT}'+name+'{LT}/h3{GT}{LT}span class="tag"{GT}'+done+'/'+ts.length+'{LT}/span{GT}{LT}/div{GT}'
  +'{LT}progress class="wide-progress" value="'+done+'" max="'+(ts.length||1)+'" aria-label="'+name+' progress"{GT}{LT}/progress{GT}'+body+'{LT}/section{GT}';
 return '{LT}details class="card settings-section mt"{GT}{LT}summary{GT}'+name+' {LT}span class="hint"{GT}· '+done+'/'+ts.length+' · '+esc(tx('Show tasks'))+'{LT}/span{GT}{LT}/summary{GT}'+body+'{LT}/details{GT}';
}
// ===== end BRICK 3.1 core =====
"""

JOURNEY_JS = r"""V.journey={title:'Progress',sub:'Foundation → Traffic → Conversion. Start focused work; submit real evidence.',render:function(){
 const ps=phases(),curK=progressCurrentPhase(ps);
 return '{LT}div id="accountStatus"{GT}'+statusHTML()+'{LT}/div{GT}'+journeySummary()
  +(ps.length?ps.map(function(e){return progressPhaseHTML(e[0],e[1],e[0]===curK);}).join(''):'{LT}div class="empty mt"{GT}Your phases and tasks will appear after your account is connected. No invented completion scores are shown.{LT}/div{GT}')
  +(S.main.generatedTasks.length?'{LT}section class="card mt"{GT}{LT}h3{GT}Tailored tasks{LT}/h3{GT}'+S.main.generatedTasks.map(taskHTML).join('')+'{LT}/section{GT}':'')
  +'{LT}div class="row mt"{GT}{LT}button class="btn btn-sm" data-act="generate-tasks"{GT}'+ic('spark')+' Generate tailored tasks{LT}/button{GT}{LT}button class="btn btn-sm" data-act="refresh-account"{GT}Refresh progress{LT}/button{GT}{LT}/div{GT}'
  +'{LT}div class="mt"{GT}'+activityHTML()+'{LT}/div{GT}';
}};"""

PATCHES = [
    ("core: pace line, phase fold, task fold helpers",
     "// ===== end BRICK 3 core =====", "after", CORE_JS),
    ("journeySummary: honest pace line replaces server trajectory",
     "${j.trajectory?.message?`{LT}div class=\"callout ${j.trajectory.status==='behind'?'warn':'acc'}\"{GT}${esc(j.trajectory.message)}{LT}/div{GT}`:''}",
     "replace", "${paceHTML(j)}"),
    ("journeySummary: hide XP until above 0",
     "['XP',int(j.xp)],", "replace", "...(num(j.xp)?[['XP',int(j.xp)]]:[]),"),
    ("journeySummary: health score placeholder",
     "['Health score',health==null?'Not available':esc(health)]", "replace",
     "['Health score',health==null?'{LT}span class=\"hint\"{GT}'+esc(tx('We’ll build this as you go'))+'{LT}/span{GT}':esc(health)]"),
    ("journeySummary: Start with Coach (the one primary button)",
     "{LT}button class=\"btn\" data-act=\"start-task\" data-id=\"${esc(j.current_task.id)}\"{GT}Start with AI Coach{LT}/button{GT}",
     "replace",
     "{LT}button class=\"btn btn-primary\" data-act=\"start-task\" data-id=\"${esc(j.current_task.id)}\"{GT}${esc(tx('Start with Coach'))}{LT}/button{GT}"),
    ("journeySummary: hide View journey self-link on Progress",
     "{LT}button class=\"btn btn-sm\" data-act=\"go\" data-v=\"journey\"{GT}View journey ${ic('arrow')}{LT}/button{GT}",
     "replace",
     "${view==='journey'?'':'{LT}button class=\"btn btn-sm\" data-act=\"go\" data-v=\"journey\"{GT}View journey '+ic('arrow')+'{LT}/button{GT}'}"),
    ("funnel: mark goal as set when the user edits it",
     "setPath(S,el.dataset.k,readVal(el));save();trackDnaEdit(el,e);", "replace",
     "setPath(S,el.dataset.k,readVal(el));if(el.dataset.k==='funnel.goal')S.funnel.goalSet=true;save();trackDnaEdit(el,e);"),
    ("funnel: legacy goals count as set",
     "if(num(old.goal))s.funnel.goal=num(old.goal);", "replace",
     "if(num(old.goal)){s.funnel.goal=num(old.goal);s.funnel.goalSet=true;}"),
    ("Tools tile: revenue goal only after the user set it",
     "if(id==='funnel'){const g=num((S.funnel||{}).goal);", "replace",
     "if(id==='funnel'){const g=(S.funnel||{}).goalSet?num(S.funnel.goal):0;"),
    ("top bar: no line breaks inside buttons and labels",
     ".top-r label{font-size:12px}.top-r select{height:32px;width:auto}", "after",
     "\n.top-r .btn,.top-r label{white-space:nowrap;flex:none}"),
    ("Arabic strings",
     "'Tools':'الأدوات',", "replace",
     "'Tools':'الأدوات','Start with Coach':'ابدأ مع المدرب','Details':'التفاصيل','Show tasks':'عرض المهام',"
     "'Current task':'المهمة الحالية','Start this task':'ابدأ هذه المهمة','We’ll build this as you go':'سنبنيه معك خطوة بخطوة',"),
]

JOURNEY_START = "V.journey={title:'Progress',"
JOURNEY_END = "\nfunction taskHTML(t){"

POST_CHECKS = ["paceHTML(j)", "progressPhaseHTML(", "goalSet", "Start with Coach", "white-space:nowrap;flex:none",
               "render:function(){\n const ps=phases(),curK="]
GONE = ["j.trajectory", "Start with AI Coach", "'Not available'", "['XP',int(j.xp)],",
        "const g=num((S.funnel||{}).goal);"]


def fail(msg):
    print("ABORTED - nothing was written.")
    print("Reason: " + msg)
    sys.exit(1)


def main():
    check_only = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = Path(args[0]) if args else Path("/root/e5-ai-coach/chat_test.html")
    backup = target.with_name(target.name + ".bak-brick3_1")
    if not target.is_file():
        fail("file not found: " + str(target))
    for name, anchor, mode, text in PATCHES + [("journey", JOURNEY_START, "x", JOURNEY_JS)]:
        for bad in (LT, GT, AMP):
            if bad in anchor or bad in text:
                fail("patch '" + name + "' contains a raw forbidden character (copy damage?)")
    src = target.read_text(encoding="utf-8")
    if MARKER in src:
        fail("Brick 3.1 marker found - this file is already patched.")
    if NEED not in src:
        fail("Brick 3 is not applied to this file. Apply patch_brick3.py first.")
    problems = []
    for name, anchor, mode, text in PATCHES:
        n = src.count(A(anchor))
        print("  [" + ("OK" if n == 1 else "FOUND " + str(n) + "x") + "] " + name)
        if n != 1:
            problems.append(name)
    ok = src.count(JOURNEY_START) == 1 and src.count(JOURNEY_END) == 1
    if ok:
        s0, e0 = src.find(JOURNEY_START), src.find(JOURNEY_END)
        ok = e0 - s0 == abs(e0 - s0) and "activityHTML()" in src[s0:e0]
    print("  [" + ("OK" if ok else "NOT FOUND") + "] Progress view: folded render")
    if not ok:
        problems.append("Progress view")
    if problems:
        fail("anchors missing or not unique: " + ", ".join(problems))
    if check_only:
        print("CHECK PASSED - all " + str(len(PATCHES) + 1) + " anchors found. Nothing written.")
        return
    s0, e0 = src.find(JOURNEY_START), src.find(JOURNEY_END)
    out = src[:s0] + A(JOURNEY_JS) + src[e0:]
    for name, anchor, mode, text in PATCHES:
        a, t = A(anchor), A(text)
        out = out.replace(a, (a + t) if mode == "after" else t, 1)
    if out.count(MARKER) != 1:
        fail("post-check: marker count is wrong")
    for needle in POST_CHECKS:
        if needle not in out:
            fail("post-check: missing " + needle)
    for needle in GONE:
        if needle in out:
            fail("post-check: old code survived: " + needle)
    shutil.copy2(target, backup)
    tmp = target.with_name(target.name + ".tmp-brick3_1")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, target)
    print("PATCHED: " + str(target) + "  (" + str(len(PATCHES) + 1) + " edits)")
    print("Backup:  " + str(backup))
    print("Rollback: cp " + str(backup) + " " + str(target) + "   then rebuild the container")


main()
