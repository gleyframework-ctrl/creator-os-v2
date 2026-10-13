#!/usr/bin/env python3
"""
BRICK 1A (frontend) - patch chat_test.html with activity tracking.

Usage:
  python3 patch_brick1a.py --check          dry run: verify anchors only, writes nothing
  python3 patch_brick1a.py                  patch /root/e5-ai-coach/chat_test.html
  python3 patch_brick1a.py /path/file.html  patch another copy

Copy-safety: this file contains NO less-than, greater-than or ampersand
characters. Where an anchor needs one, it is written as a placeholder
({GT}) and rebuilt with chr() at runtime. The inserted JavaScript uses no
arrow functions and no comparison signs at all.
"""
import os
import shutil
import sys
from pathlib import Path

LT = chr(60)
GT = chr(62)
AMP = chr(38)

args = [a for a in sys.argv[1:] if a != "--check"]
CHECK_ONLY = "--check" in sys.argv
TARGET = Path(args[0]) if args else Path("/root/e5-ai-coach/chat_test.html")
BACKUP = TARGET.with_name(TARGET.name + ".bak-brick1a")
MARKER = "BRICK 1A: activity tracking"


def A(s):
    """Rebuild an anchor/payload: {GT} becomes the greater-than sign."""
    return s.replace("{GT}", GT)


CORE_JS = r"""// ===== BRICK 1A: activity tracking (behavior/UX only; never throws, never blocks UI) =====
const EV_URL='/api/activity/batch',EV_MAX_QUEUE=200,EV_BATCH=50,EV_HIDE_BATCH=20,EV_HIDE_REQUESTS=2;
let _evQueue=[],_evFlushing=false,_evStarted=false,_evFirstCreationSent=false;
function evReady(){if(!SESSION.member_id)return false;if(!SESSION.csrf_token)return false;return true;}
function evTrim(){_evQueue=_evQueue.slice(-EV_MAX_QUEUE);}
function track(event_type,meta){
 try{const m=Object.assign({},isObj(meta)?meta:{});m.ts=Date.now();_evQueue.push({event_type:String(event_type),meta:m,_r:0});evTrim();}catch(e){}
}
function evBody(batch){return JSON.stringify({events:batch.map(function(x){return {event_type:x.event_type,meta:x.meta};})});}
function evRequeue(batch){
 try{const again=batch.filter(function(x){return !x._r;});again.forEach(function(x){x._r=1;});_evQueue=again.concat(_evQueue);evTrim();}catch(e){}
}
async function flushEvents(){
 if(_evFlushing)return;
 try{
  if(!_evQueue.length)return;if(navigator.onLine===false)return;if(!evReady())return;
  _evFlushing=true;const batch=_evQueue.splice(0,EV_BATCH);
  try{
   const r=await fetch(EV_URL,{method:'POST',credentials:'same-origin',headers:jsonHeaders(),body:evBody(batch)});
   if([502,503,504].includes(r.status))evRequeue(batch);
  }catch(e){evRequeue(batch);}
 }catch(e){}
 finally{_evFlushing=false;}
}
function flushEventsOnHide(){
 try{
  if(!evReady())return;let sent=0;
  while(sent!==EV_HIDE_REQUESTS){
   if(!_evQueue.length)break;const batch=_evQueue.splice(0,EV_HIDE_BATCH);sent++;
   fetch(EV_URL,{method:'POST',keepalive:true,credentials:'same-origin',headers:jsonHeaders(),body:evBody(batch)}).catch(function(){});
  }
 }catch(e){}
}
function startActivityTracking(){
 try{
  if(_evStarted)return;_evStarted=true;
  setInterval(function(){flushEvents();},10000);
  window.addEventListener('pagehide',flushEventsOnHide);
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='hidden')flushEventsOnHide();});
 }catch(e){}
}
function trackRoute(v,first,changed){
 try{
  if(v==='home'){if(first||changed)track('today_viewed',{});return;}
  if(!changed)return;const m={tool:String(v)};
  if(v==='funnel')m.tab=String(S.ui.funnelTab||'model');
  if(v==='community')m.sub=String(S.community.tool||'audit');
  track('tool_opened',m);
 }catch(e){}
}
function trackTab(group,prev,next){try{if(String(prev)!==String(next))track('tool_opened',{tool:group+':'+String(next)});}catch(e){}}
function trackDnaEdit(el,e){
 try{
  if(_evFirstCreationSent)return;if(e.type!=='change')return;
  const k=String(el.dataset.k||'');if(k.indexOf('dna.')!==0)return;
  if(String(el.value==null?'':el.value).trim()==='')return;
  _evFirstCreationSent=true;track('first_creation_saved',{field:k.slice(4)});
 }catch(err){}
}
function trackOnboarding(step,o,el){
 try{
  const m={step:step,stage:String(o.stage||''),bottleneck:String(o.bottleneck||''),hours:String(o.hours||''),traffic:String(o.traffic||'')};
  if(step===1){let regen=false;if(el){if(el.dataset)regen=el.dataset.act==='on-regenerate';}m.regenerated=regen;}
  track('onboarding_answered',m);
 }catch(e){}
}
function evHasRevenue(amount){if(amount==null)return false;return Math.max(0,num(amount))!==0;}
// ===== end BRICK 1A core =====
"""

# (name, anchor, mode, text)   mode: before | after | replace
PATCHES = [
    ("core: track + queue + flush",
     "async function apiJSON(url,options={}){", "before", CORE_JS),
    ("init: start tracking after bootstrapSession",
     "await bootstrapSession();S=load();", "replace",
     "await bootstrapSession();startActivityTracking();S=load();"),
    ("#1  onboarding_answered step 1",
     "o.speed_profile=d.speed_profile||'steady';save();onboardingModal(2);", "replace",
     "o.speed_profile=d.speed_profile||'steady';save();trackOnboarding(1,o,el);onboardingModal(2);"),
    ("#1b onboarding_answered step 3 (Confirm and begin)",
     "S.main.needsOnboarding=false;proofFiles=[];addActivity('Coach setup completed');", "replace",
     "trackOnboarding(3,o,null);S.main.needsOnboarding=false;proofFiles=[];addActivity('Coach setup completed');"),
    ("#2  first_creation_saved",
     "setPath(S,el.dataset.k,readVal(el));save();", "replace",
     "setPath(S,el.dataset.k,readVal(el));save();trackDnaEdit(el,e);"),
    ("#3  today_viewed + #9 tool_opened (views)",
     "const changed=v!==view;view=v;render();", "replace",
     "const changed=v!==view;view=v;render();trackRoute(v,first,changed);"),
    ("#9  tool_opened funnel tabs",
     A("ACT.ftab=el={GT}{S.ui.funnelTab=el.dataset.v;save();render();};"), "replace",
     "ACT.ftab=function(el){const prev=S.ui.funnelTab||'model';S.ui.funnelTab=el.dataset.v;save();render();trackTab('funnel',prev,el.dataset.v);};"),
    ("#9  tool_opened community tools",
     A("ACT.ctool=el={GT}{S.community.tool=el.dataset.v;save();render();};"), "replace",
     "ACT.ctool=function(el){const prev=S.community.tool||'audit';S.community.tool=el.dataset.v;save();render();trackTab('community',prev,el.dataset.v);};"),
    ("#4  task_started",
     A("ACT['start-task']=el={GT}{const t=taskById(el.dataset.id||el.dataset.v);if(!t){toast('Refresh your journey before starting this task.');return;}"),
     "after",
     "track('task_started',{task_id:String(t.id),task_name:String(t.name||'').slice(0,120),from:String(view)});"),
    ("#5  task_submitted",
     A("if(links.some(x={GT}!safeURL(x)))throw new Error('Evidence links must be complete http or https URLs.');"),
     "after",
     "track('task_submitted',{task_id:String(S.main.journey?.current_task?.id||''),char_count:text.length});"),
    ("#6/#7 task_passed / task_failed",
     "if(d.score==null)throw new Error('The server did not confirm a review score.');",
     "after",
     "track(d.task_unlocked?'task_passed':'task_failed',{task_id:String(t.id),score:num(d.score)});"),
    ("#8  coach_message_sent",
     "try{requireAccount();}catch(e){toast(e.message);return;}sending=true;", "replace",
     "try{requireAccount();}catch(e){toast(e.message);return;}track('coach_message_sent',{length:text.length,mode:String(S.main.mode||''),retry:!!textOverride});sending=true;"),
    ("#10 win_logged",
     "if(d.error||d.ok===false)throw new Error(d.error||'Win could not be saved.');",
     "after",
     "track('win_logged',{has_revenue:evHasRevenue(amount),currency:String(currency||'')});"),
]

POST_CHECKS = [
    "startActivityTracking();S=load();", "trackRoute(v,first,changed);", "trackDnaEdit(el,e);",
    "trackOnboarding(1,o,el);", "trackOnboarding(3,o,null);", "trackTab('funnel'",
    "trackTab('community'", "track('task_started'", "track('task_submitted'",
    "'task_passed':'task_failed'", "track('coach_message_sent'", "track('win_logged'",
]


def fail(msg):
    print("ABORTED - nothing was written.")
    print("Reason: " + msg)
    sys.exit(1)


def main():
    if not TARGET.is_file():
        fail("file not found: " + str(TARGET))
    src = TARGET.read_text(encoding="utf-8")
    if MARKER in src:
        fail("Brick 1A marker found - this file is already patched.")

    escaped = (AMP + "gt;", AMP + "lt;", AMP + "amp;")
    for name, anchor, mode, text in PATCHES:
        for bad in (LT, GT, AMP):
            if bad in text:
                fail("inserted code for '" + name + "' contains a forbidden character (copy damage?)")
        for e in escaped:
            if e in anchor:
                fail("anchor for '" + name + "' contains HTML-escaped text (copy damage?)")

    problems = []
    for name, anchor, mode, text in PATCHES:
        n = src.count(anchor)
        print("  [" + ("OK" if n == 1 else "FOUND " + str(n) + "x") + "] " + name)
        if n != 1:
            problems.append(name)
    if problems:
        fail("anchors missing or not unique: " + ", ".join(problems))

    if CHECK_ONLY:
        print("CHECK PASSED - all " + str(len(PATCHES)) + " anchors found exactly once. Nothing written.")
        return

    out = src
    for name, anchor, mode, text in PATCHES:
        if mode == "before":
            new = text + anchor
        elif mode == "after":
            new = anchor + text
        else:
            new = text
        out = out.replace(anchor, new, 1)

    if out.count(MARKER) != 1:
        fail("post-check: marker count is wrong")
    for needle in POST_CHECKS:
        if needle not in out:
            fail("post-check: missing " + needle)

    shutil.copy2(TARGET, BACKUP)
    tmp = TARGET.with_name(TARGET.name + ".tmp-brick1a")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, TARGET)
    print("PATCHED: " + str(TARGET) + "  (+" + str(len(out) - len(src)) + " bytes, " + str(len(PATCHES)) + " edits)")
    print("Backup:  " + str(BACKUP))
    print("Rollback: cp " + str(BACKUP) + " " + str(TARGET) + "   then rebuild the container")


main()
