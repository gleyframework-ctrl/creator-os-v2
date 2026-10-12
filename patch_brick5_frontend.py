#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brick 5 frontend: Coach = one input box (chat_test.html only).

Usage (run from /root/e5-ai-coach):
  python3 patch_brick5_frontend.py --check   dry run: checks prerequisites and anchors, writes nothing
  python3 patch_brick5_frontend.py           applies the patch (backup: chat_test.html.bak-brick5)

Copy-safe: this file contains no less-than, greater-than or ampersand characters.
They are stored as tokens and rebuilt with chr() when the script runs:
  @@LT@@ is chr(60), @@GT@@ is chr(62), @@AMP@@ is chr(38)
"""
import shutil
import sys

TARGET = "chat_test.html"
BACKUP = TARGET + ".bak-brick5"
MARKER = "BRICK 5: COACH = ONE INPUT BOX"
LT, GT, AMP = chr(60), chr(62), chr(38)


def dec(s):
    return s.replace("@@LT@@", LT).replace("@@GT@@", GT).replace("@@AMP@@", AMP)


PREREQS = [('Brick 1A', 'BRICK 1A'), ('Sprint 1.5 A+B', 'SPRINT 1.5 A+B'), ('Brick 4 (first win)', 'BRICK 4: FIRST WIN')]

# (name, old, new, expected_count)
EDITS = [
    ('send body adds beginner flag', r'''const body={message:prompt,mode:S.main.mode,member_id:memberId(),history};''', r'''const body={message:prompt,mode:S.main.mode,member_id:memberId(),history,beginner:guidedOn()};''', 1),
    ('Brick 5 block before boot', r'''// ===== boot =====''', r'''// ===== BRICK 5: COACH = ONE INPUT BOX (guided mode only; full controls return when guided mode is off) =====
Object.assign(UI_AR,{'More':'المزيد','More actions':'إجراءات أخرى',"Help me with today's move:":'ساعدني في حركة اليوم:','Help me with this task:':'ساعدني في هذه المهمة:',"Tell your coach where you're stuck.":'أخبر مدربك أين أنت عالق.',"Tell your coach where you're stuck…":'أخبر مدربك أين أنت عالق…',"Your coach already knows your offer and today's task.":'مدربك يعرف عرضك ومهمة اليوم.',"Your coach already knows today's task.":'مدربك يعرف مهمة اليوم.','Your coach':'مدربك','You':'أنت','Copy':'نسخ','Coaching mode':'وضع التدريب','Read answers aloud':'اقرأ الإجابات بصوت عالٍ','Clear history':'مسح المحادثة','Voice input':'إدخال صوتي','Read aloud':'قراءة بصوت عالٍ','Tasks':'مهام','See the brief':'عرض التعليمات','What would you like to work on?':'على ماذا تريد أن تعمل؟','Other ideas':'أفكار أخرى'});
let _b5MoreOpen=false;
// Hidden task context: kept until the task is completed, the history is cleared, or another task is started.
function b5Ctx(){
 try{
  const c=S.main.taskContext;if(!isObj(c))return null;
  const j=S.main.journey;
  if(isObj(j)){const done=(Array.isArray(j.tasks_completed)?j.tasks_completed:[]).map(String);if(done.indexOf(String(c.id))!==-1){S.main.taskContext=null;save();return null;}}
  return c;
 }catch(e){return null;}
}
// Auto mode (guided only): task session when started from a task, otherwise general coach. A manual pick in More wins.
function b5AutoMode(){try{if(!guidedOn())return;if(S.main.modeManual===true)return;S.main.mode=b5Ctx()?'accountability':'coach';}catch(e){}}
const _b5OrigBrief=chatBrief;
chatBrief=function(text){
 const c=b5Ctx();if(!c)return _b5OrigBrief(text);
 const mode=MODES.find(function(m){return m[0]===S.main.mode;})||MODES[0],N='\n';
 const dels=(Array.isArray(c.deliverables)?c.deliverables:[]).filter(Boolean).map(function(x){return '- '+x;}).join(N);
 return langOnly(mode[2]+N+N+dnaBlock()+N+N+'Current journey task: '+(S.main.journey?.current_task?.name||c.name||'not connected')+N+N+'=== TASK DETAILS (added by the app, not typed by the user) ==='+N+'Task: '+c.name+N+'Why it matters: '+(c.why||'')+N+'Deliverables:'+N+dels+N+'Work on one deliverable at a time and ask only for information you genuinely need.'+N+N+'=== USER MESSAGE ==='+N+text);
};
const _b5OrigSend=sendCoach;
sendCoach=function(textOverride){b5AutoMode();return _b5OrigSend(textOverride);};
document.addEventListener('change',function(e){try{if(e.target){if(e.target.id==='coachMode'){S.main.modeManual=true;save();}}}catch(err){}});
document.addEventListener('toggle',function(e){try{if(e.target){if(e.target.id==='coachMore')_b5MoreOpen=!!e.target.open;}}catch(err){}},true);
function b5MsgHTML(m){
 const user=m.role==='user';
 let h='@@LT@@article class="coach-message'+(user?' user':'')+'" data-message="'+esc(m.id)+'" dir="auto"@@GT@@@@LT@@div class="message-by"@@GT@@'+esc(tx(user?'You':'Coach'))+' @@LT@@span class="hint"@@GT@@'+ago(m.at)+'@@LT@@/span@@GT@@@@LT@@/div@@GT@@@@LT@@div class="md"@@GT@@'+(user?esc(m.content).replace(/\n/g,'@@LT@@br@@GT@@'):md(m.content))+'@@LT@@/div@@GT@@';
 if(m.error)h+='@@LT@@div class="callout bad"@@GT@@'+esc(m.error)+'@@LT@@/div@@GT@@@@LT@@button class="btn btn-sm" data-act="chat-retry" data-id="'+esc(m.id)+'"@@GT@@Retry@@LT@@/button@@GT@@';
 if(!user){if(m.content){
  const id=esc(m.id);
  h+='@@LT@@div class="row mt-s"@@GT@@@@LT@@button class="btn btn-sm" data-act="chat-copy" data-id="'+id+'"@@GT@@'+ic('copy')+' '+esc(tx('Copy'))+'@@LT@@/button@@GT@@'
   +'@@LT@@details style="display:inline-block"@@GT@@@@LT@@summary class="btn btn-sm btn-ghost" style="list-style:none" aria-label="'+esc(tx('More actions'))+'" title="'+esc(tx('More actions'))+'"@@GT@@⋯@@LT@@/summary@@GT@@'
   +'@@LT@@div class="row mt-s"@@GT@@@@LT@@button class="btn btn-sm" data-act="chat-save" data-id="'+id+'"@@GT@@'+ic('save')+' '+esc(tx('Save'))+'@@LT@@/button@@GT@@@@LT@@button class="btn btn-sm" data-act="chat-tasks" data-id="'+id+'"@@GT@@'+ic('list')+' '+esc(tx('Tasks'))+'@@LT@@/button@@GT@@@@LT@@button class="btn btn-sm" data-act="chat-read" data-id="'+id+'"@@GT@@'+esc(tx('Read aloud'))+'@@LT@@/button@@GT@@@@LT@@/div@@GT@@'
   +'@@LT@@details class="prompt-box"@@GT@@@@LT@@summary@@GT@@'+esc(tx('See the brief'))+'@@LT@@/summary@@GT@@@@LT@@pre@@GT@@'+esc(m.prompt||'Imported conversation')+'@@LT@@/pre@@GT@@@@LT@@/details@@GT@@@@LT@@/details@@GT@@@@LT@@/div@@GT@@';
 }}
 return h+'@@LT@@/article@@GT@@';
}
function b5EmptyHTML(){
 const known=String(S.dna.offer||'').trim()?"Your coach already knows your offer and today's task.":"Your coach already knows today's task.";
 return '@@LT@@div class="coach-empty"@@GT@@@@LT@@span class="eyebrow"@@GT@@'+ic('spark')+' '+esc(tx('Your coach'))+'@@LT@@/span@@GT@@@@LT@@h2@@GT@@'+esc(tx("Tell your coach where you're stuck."))+'@@LT@@/h2@@GT@@@@LT@@p class="muted"@@GT@@'+esc(tx(known))+'@@LT@@/p@@GT@@@@LT@@div class="row"@@GT@@'+coachMoveStarter()+'@@LT@@/div@@GT@@@@LT@@/div@@GT@@';
}
const _b5Messages=messagesHTML;
messagesHTML=function(){if(!guidedOn())return _b5Messages();return S.main.chat.length?S.main.chat.map(b5MsgHTML).join(''):b5EmptyHTML();};
const B5_IDEAS=['Improve my offer and explain why','Plan my next 7 days'];
function b5ChatHTML(){
 const modes=MODES.map(function(x){return '@@LT@@option value="'+x[0]+'"'+(S.main.mode===x[0]?' selected':'')+'@@GT@@'+esc(x[1])+'@@LT@@/option@@GT@@';}).join('');
 return '@@LT@@div class="coach-layout"@@GT@@'
  +'@@LT@@div class="coach-history" id="coachHistory" role="log" aria-label="Coach conversation"@@GT@@'+messagesHTML()+'@@LT@@/div@@GT@@@@LT@@div class="sr-only" id="chatAnnounce" role="status" aria-live="polite"@@GT@@@@LT@@/div@@GT@@'
  +'@@LT@@div class="card composer"@@GT@@@@LT@@label class="lab" for="coachInput"@@GT@@'+esc(tx('What would you like to work on?'))+'@@LT@@/label@@GT@@@@LT@@textarea id="coachInput" data-k="main.draft" rows="3" maxlength="12000" dir="auto" placeholder="'+esc(tx("Tell your coach where you're stuck…"))+'"@@GT@@'+esc(S.main.draft)+'@@LT@@/textarea@@GT@@'
  +'@@LT@@div class="row between mt-s"@@GT@@@@LT@@span class="hint"@@GT@@Enter to send · Shift+Enter for a new line@@LT@@/span@@GT@@@@LT@@div class="row"@@GT@@@@LT@@button class="btn btn-primary" data-act="chat-send"'+(sending?' disabled':'')+'@@GT@@'+(sending?'Thinking…':esc(tx('Send')))+' '+ic('arrow')+'@@LT@@/button@@GT@@'+(sending?'@@LT@@button class="btn" data-act="chat-stop"@@GT@@Stop@@LT@@/button@@GT@@':'')+'@@LT@@/div@@GT@@@@LT@@/div@@GT@@@@LT@@/div@@GT@@'
  +'@@LT@@details class="card" id="coachMore"'+(_b5MoreOpen?' open':'')+'@@GT@@@@LT@@summary class="hint" style="cursor:pointer"@@GT@@'+esc(tx('More'))+' ⋯@@LT@@/summary@@GT@@'
  +'@@LT@@div class="coach-toolbar" style="padding:12px 0 0"@@GT@@@@LT@@label for="coachMode" class="lab"@@GT@@'+esc(tx('Coaching mode'))+'@@LT@@/label@@GT@@@@LT@@select id="coachMode" data-k="main.mode" aria-label="Coaching mode"@@GT@@'+modes+'@@LT@@/select@@GT@@@@LT@@label class="row"@@GT@@@@LT@@input type="checkbox" data-k="main.tts"'+(S.main.tts?' checked':'')+'@@GT@@ '+esc(tx('Read answers aloud'))+'@@LT@@/label@@GT@@@@LT@@button class="btn btn-sm" data-act="voice"@@GT@@'+esc(tx('Voice input'))+'@@LT@@/button@@GT@@@@LT@@button class="btn btn-sm" data-act="chat-clear"@@GT@@'+esc(tx('Clear history'))+'@@LT@@/button@@GT@@@@LT@@/div@@GT@@'
  +'@@LT@@p class="hint mt"@@GT@@'+esc(tx('Other ideas'))+'@@LT@@/p@@GT@@@@LT@@div class="row mt-s"@@GT@@'+B5_IDEAS.map(function(p){return '@@LT@@button class="btn btn-sm starter" data-act="chat-starter" data-text="'+esc(p)+'"@@GT@@'+esc(p)+' '+ic('arrow')+'@@LT@@/button@@GT@@';}).join('')+'@@LT@@/div@@GT@@@@LT@@/details@@GT@@@@LT@@/div@@GT@@';
}
const _b5ChatRender=V.chat.render;
V.chat.render=function(){if(!guidedOn())return _b5ChatRender.call(this);return b5ChatHTML();};
// Start a task: short visible message in the box; the task details travel in the hidden brief.
const _b5OrigStart=ACT['start-task'];
ACT['start-task']=function(el,e){
 const id=String(el.dataset.id||el.dataset.v||'');
 if(fwEligible(id))return _b5OrigStart(el,e);
 const t=taskById(id);if(!t){toast('Refresh your journey before starting this task.');return;}
 track('task_started',{task_id:String(t.id),task_name:String(t.name||'').slice(0,120),from:String(view),via:evTakeVia()});
 const isCur=String(S.main.journey?.current_task?.id||'')===String(t.id);
 S.main.taskContext={id:String(t.id),name:String(t.name||''),why:String(t.why||''),deliverables:(t.deliverables||[t.deliverable]).filter(Boolean).map(String).slice(0,8)};
 S.main.modeManual=false;S.main.mode='accountability';
 S.main.draft=tx(isCur?"Help me with today's move:":'Help me with this task:')+' '+String(t.name||'')+'.';
 save();go('chat');
 setTimeout(function(){const i=$('#coachInput');if(i){i.focus();try{i.setSelectionRange(i.value.length,i.value.length);}catch(err){}}},20);
};
ACT['chat-clear']=function(){if(sending){toast('Stop the active response first.');return;}askConfirm('Clear chat history?','Only this device’s chat history will be cleared. Saved Library answers remain.',function(){S.main.chat=[];S.main.taskContext=null;S.main.modeManual=false;save();render();});};
// ===== end BRICK 5 core =====

// ===== boot =====''', 1),
]


def fail(msg):
    print("ABORTED: " + msg)
    print("Nothing was written.")
    sys.exit(1)


def main():
    check_only = "--check" in sys.argv
    try:
        own = open(__file__, encoding="utf-8").read()
    except Exception:
        own = ""
    if LT in own or GT in own or AMP in own:
        fail("this script was altered in transit (raw angle bracket or ampersand found). Download it again.")
    try:
        text = open(TARGET, encoding="utf-8").read()
    except Exception as e:
        fail("cannot read " + TARGET + ": " + str(e))
    if MARKER in text:
        fail("Brick 5 is already applied to " + TARGET + ".")
    for label, needle in PREREQS:
        if needle not in text:
            fail(label + " is not applied to " + TARGET + ". Apply it first.")
    new = text
    for name, old, rep, count in EDITS:
        old, rep = dec(old), dec(rep)
        found = new.count(old)
        if found != count:
            fail("anchor '" + name + "' found " + str(found) + " time(s), expected " + str(count) + ".")
        new = new.replace(old, rep)
    if MARKER not in new:
        fail("marker missing after patching.")

    if check_only:
        print("CHECK OK: all prerequisites and " + str(len(EDITS)) + " anchors found. Run without --check to apply.")
        return
    shutil.copyfile(TARGET, BACKUP)
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new)
    print("PATCHED " + TARGET + " (" + str(len(text)) + " -" + chr(62) + " " + str(len(new)) + " bytes). Backup: " + BACKUP)


if __name__ == "__main__":
    main()
