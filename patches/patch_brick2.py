#!/usr/bin/env python3
"""
BRICK 2 - Today screen (beginner-first home). Patches chat_test.html only.
V.home (the full Command Center) is untouched and stays at #command.
Requires Brick 1A (it edits the 1A route tracking). Works with Brick 1B applied.

Usage:
  python3 patch_brick2.py --check          dry run: verify every anchor, writes nothing
  python3 patch_brick2.py                  patch /root/e5-ai-coach/chat_test.html
  python3 patch_brick2.py /path/file.html  patch another copy
  python3 patch_brick2.py --sql            print the two Brick 2 metric queries

Copy-safety: this file contains NO less-than, greater-than or ampersand characters.
Anchors and inserted code write them as {LT} and {GT}; they are rebuilt with chr()
at runtime. The inserted JavaScript uses no arrow functions and no comparison signs.
Nothing is written unless every anchor is found exactly once.
"""
import os
import shutil
import sys
from pathlib import Path

LT = chr(60)
GT = chr(62)
AMP = chr(38)
MARKER = "BRICK 2: Today screen"
NEED_1A = "BRICK 1A: activity tracking"


def A(s):
    """Rebuild placeholders: {LT} and {GT} become the real characters."""
    return s.replace("{LT}", LT).replace("{GT}", GT)


SQL = """-- Brick 2 metrics. Run in Supabase.
-- IMPORTANT: replace 2026-10-09 19:00+00 with your Brick 2 deploy time (UTC).
-- Before Brick 2, today_viewed meant the full Command Center, so older rows must not count.

-- 1) Click-through: Today views followed within 10 minutes by an action started from Today.
--    Target: 50 percent or more.
WITH v AS (
  SELECT id, member_id, created_at FROM events
  WHERE event_type = 'today_viewed'
    AND created_at BETWEEN TIMESTAMPTZ '2026-10-09 19:00+00' AND NOW()
),
x AS (
  SELECT v.id, EXISTS (
    SELECT 1 FROM events e
    WHERE e.member_id = v.member_id
      AND jsonb_extract_path_text(e.meta, 'via') = 'today'
      AND e.created_at BETWEEN v.created_at AND v.created_at + INTERVAL '10 minutes'
  ) AS acted
  FROM v
)
SELECT COUNT(*) AS today_views,
       COUNT(*) FILTER (WHERE acted) AS views_with_action,
       ROUND(100.0 * COUNT(*) FILTER (WHERE acted) / NULLIF(COUNT(*), 0), 1) AS click_through_pct
FROM x;

-- 2) Escape hatch: "Show everything" clicks divided by Today views.
--    Target: under 30 percent. Above that, Today hides something people need.
SELECT
  COUNT(*) FILTER (WHERE event_type = 'today_viewed') AS today_views,
  COUNT(*) FILTER (WHERE event_type = 'tool_opened'
                     AND jsonb_extract_path_text(meta, 'tool') = 'home'
                     AND jsonb_extract_path_text(meta, 'via') = 'today') AS show_everything_clicks,
  ROUND(100.0 * COUNT(*) FILTER (WHERE event_type = 'tool_opened'
                                   AND jsonb_extract_path_text(meta, 'tool') = 'home'
                                   AND jsonb_extract_path_text(meta, 'via') = 'today')
        / NULLIF(COUNT(*) FILTER (WHERE event_type = 'today_viewed'), 0), 1) AS escape_pct
FROM events
WHERE created_at BETWEEN TIMESTAMPTZ '2026-10-09 19:00+00' AND NOW();
"""


TODAY_JS = r"""// ===== BRICK 2: Today screen (beginner-first home; V.home stays the full Command Center) =====
let _todayVia=null;
// Capture phase: runs before the data-act handler, so the next task_started / tool_opened carries via:'today'.
document.addEventListener('click',function(e){try{const el=e.target.closest?e.target.closest('[data-via]'):null;if(el)_todayVia={v:String(el.dataset.via||''),at:Date.now()};}catch(err){}},true);
function evTakeVia(){try{const x=_todayVia;_todayVia=null;if(!x)return undefined;if(Math.max(Date.now()-x.at,5000)!==5000)return undefined;return x.v||undefined;}catch(e){return undefined;}}
function todayHomeDefault(){return S.ui.homeFull===true?'home':'today';}
function todayHref(){return S.ui.homeFull===true?'command':'today';}
function navActive(k){if(k==='today')return view==='today'||view==='home';return view===k;}
function todayGreeting(){
 const p=Math.floor(new Date().getHours()/6);const g=p===1?'Good morning':p===2?'Good afternoon':'Good evening';
 const first=String((S.main.profile||{}).name||'').trim().split(/\s+/)[0]||'';
 return tx(g)+(first?(S.ui.lang==='ar'?'، ':', ')+first:'')+'.';
}
function todayProgress(){
 const j=S.main.journey;if(!isObj(j))return '';
 const total=phases().reduce(function(a,x){const t=(x[1]||{}).tasks;return a+(Array.isArray(t)?t.length:0);},0);
 const done=Math.max(0,num(j.tasks_completed_count));
 let line=tx('Day')+' '+int(j.current_day||1)+' '+tx('of')+' 90 · ',bar='';
 if(total){
  line+=int(done)+' '+tx('of')+' '+int(total)+' '+tx('tasks');
  bar='{LT}div class="progress" style="margin-top:8px" role="progressbar" aria-label="Journey tasks" aria-valuemin="0" aria-valuemax="'+int(total)+'" aria-valuenow="'+int(done)+'"{GT}{LT}i style="width:'+clamp(done/total*100,0,100).toFixed(1)+'%"{GT}{LT}/i{GT}{LT}/div{GT}';
 }else line+=int(done)+' '+tx('tasks done');
 return '{LT}div style="margin-bottom:20px"{GT}{LT}p class="muted small" style="margin:0"{GT}'+esc(line)+'{LT}/p{GT}'+bar+'{LT}/div{GT}';
}
function todayEyebrow(fw){return '{LT}span class="eyebrow"{GT}'+ic('bolt',13)+' '+esc(tx("Today's move"))+(fw?' · '+esc(fw):'')+'{LT}/span{GT}';}
function todaySkeleton(){
 return '{LT}div class="card hero" role="status"{GT}{LT}span class="eyebrow"{GT}'+ic('bolt',13)+' '+esc(tx("Finding today's move…"))+'{LT}/span{GT}{LT}div class="skel mt"{GT}{LT}i style="width:55%;height:18px"{GT}{LT}/i{GT}{LT}i{GT}{LT}/i{GT}{LT}i style="width:35%"{GT}{LT}/i{GT}{LT}/div{GT}{LT}/div{GT}';
}
function todayMoveCard(h){
 return '{LT}div class="card hero"{GT}'+todayEyebrow(h.fw)+'{LT}h2{GT}'+esc(h.t)+'{LT}/h2{GT}{LT}p class="muted"{GT}'+esc(h.w)+'{LT}/p{GT}'
  +'{LT}button class="btn btn-primary btn-lg" data-act="'+esc(h.act)+'" data-v="'+esc(h.v||'')+'" data-via="today"{GT}'+esc(h.cta)+' '+ic('arrow')+'{LT}/button{GT}{LT}/div{GT}';
}
function todayDnaCard(h){
 return '{LT}div class="card hero"{GT}'+todayEyebrow(h.fw)+'{LT}h2{GT}'+esc(h.t)+'{LT}/h2{GT}{LT}p class="muted"{GT}'+esc(h.w)+'{LT}/p{GT}'
  +'{LT}div class="form-grid"{GT}'+fld('Niche','dna.niche',{ph:'e.g. fitness for busy moms',span:'span-all'})+fld('Who you help','dna.avatar',{ph:'e.g. moms 30–45 with no time for the gym',span:'span-all',area:true,rows:2})+fld('Your offer','dna.offer',{ph:'e.g. 12-week home training program',span:'span-all'})+'{LT}/div{GT}'
  +'{LT}div class="row mt"{GT}{LT}button class="btn btn-primary btn-lg" data-act="today-dna-save"{GT}'+esc(tx('Save and continue'))+' '+ic('arrow')+'{LT}/button{GT}{LT}/div{GT}{LT}/div{GT}';
}
// One card: setup first, then a skeleton only while the journey is genuinely missing, then nextMoves()[0].
function todayCard(){
 if(S.main.needsOnboarding===true)return todayMoveCard({t:'Personalize your coach',w:'Three short steps: your situation, your strategy, then confirm. Your coach uses it in every answer.',cta:'Start setup (3 steps)',act:'onboard',v:'',fw:'Setup'});
 if(!S.main.journey){if(!REMOTE.checked)return todaySkeleton();}
 const h=nextMoves()[0];
 if(h.act==='focus')return todayDnaCard(h);
 return todayMoveCard(h);
}
V.today={title:'Today',sub:'One move at a time. Everything else is one click away.',render:function(){
 if(!SESSION.member_id){
  const st=statusHTML();
  return '{LT}div id="accountStatus" style="max-width:760px"{GT}'+(st||'{LT}div class="callout warn"{GT}{LT}span{GT}Sign in through Whop to load your workspace.{LT}/span{GT}{LT}a class="btn btn-sm" href="/auth/whop"{GT}Sign in with Whop{LT}/a{GT}{LT}/div{GT}')+'{LT}/div{GT}';
 }
 let out='{LT}div style="max-width:760px"{GT}{LT}h2 style="margin:0 0 6px;font-size:22px;font-weight:600"{GT}'+esc(todayGreeting())+'{LT}/h2{GT}'+todayProgress();
 if(REMOTE.error)out+='{LT}div class="callout warn"{GT}{LT}span{GT}'+esc(REMOTE.error)+'{LT}/span{GT}{LT}button class="btn btn-sm" data-act="refresh-account"{GT}Retry connection{LT}/button{GT}{LT}/div{GT}';
 out+=todayCard();
 out+='{LT}a href="#command" class="btn btn-ghost" data-via="today"{GT}'+esc(tx('Show everything'))+(S.ui.lang==='ar'?' ←':' →')+'{LT}/a{GT}{LT}/div{GT}';
 return out;
}};
ACT['today-dna-save']=function(){
 const d=S.dna;const miss=['niche','avatar','offer'].filter(function(k){return !String(d[k]==null?'':d[k]).trim();});
 if(miss.length){toast('Fill in all three fields to continue.');const f=document.getElementById('f_dna_'+miss[0]);if(f)f.focus();return;}
 clearTimeout(saveTimer);persistNow();
 try{if(!_evFirstCreationSent){_evFirstCreationSent=true;track('first_creation_saved',{field:'today_card'});}}catch(e){}
 toast('Business DNA saved. Here is your next move.');render();
 try{window.scrollTo(0,0);}catch(e){}
};
// ===== end BRICK 2 core =====
"""

SETTINGS_TOGGLE = (
    '{LT}label class="row mt"{GT}{LT}input type="checkbox" data-k="ui.homeFull" data-full'
    "${S.ui.homeFull===true?' checked':''}"
    '{GT} Show full Command Center by default{LT}/label{GT}'
    '{LT}p class="hint mt-s"{GT}Applies to this device only. When on, the first sidebar item opens the full '
    'Command Center; the Today screen stays at #today.{LT}/p{GT}'
)

AR_STRINGS = (
    "'Daily standup':'المراجعة اليومية',"
    "\"Show everything\":'عرض كل شيء',\"Today's move\":'حركة اليوم','Day':'يوم','of':'من','tasks':'مهام',"
    "'tasks done':'مهام مكتملة',\"Finding today's move…\":'جاري إيجاد حركة اليوم…',"
    "'Good morning':'صباح الخير','Good afternoon':'مساء الخير','Good evening':'مساء الخير',"
    "'Save and continue':'احفظ وتابع'};"
)

# (name, anchor, mode, text) - raw, placeholders rebuilt by A() at runtime.  mode: before | after | replace
PATCHES = [
    ("core: Today view, helpers, DNA save action",
     "V.journey={title:'My Journey',", "before", TODAY_JS),
    ("route: default landing is Today (or full Command Center if the setting is on)",
     "if(!V[v])v='home';", "replace", "if(!V[v])v=todayHomeDefault();"),
    ("1A trackRoute: today_viewed fires for Today; home only when navigated to",
     "if(v==='home'){if(first||changed)track('today_viewed',{});return;}", "replace",
     "if(v==='today'){if(first||changed)track('today_viewed',{});return;}if(v==='home'){if(first)return;}"),
    ("1A trackRoute: via on tool_opened",
     "if(v==='community')m.sub=String(S.community.tool||'audit');", "after",
     "const via=evTakeVia();if(via)m.via=via;"),
    ("1A task_started: via",
     "from:String(view)});", "replace", "from:String(view),via:evTakeVia()});"),
    ("sidebar: Command Center becomes Today (same slot, same icon)",
     "const NAV=[['home','Command Center','home'],", "replace", "const NAV=[['today','Today','home'],"),
    ("sidebar: Today links to the default screen",
     "(n[0]==='home'?'command':n[0])", "replace", "(n[0]==='today'?todayHref():n[0])"),
    ("sidebar: Today highlighted on Today and full Command Center",
     "(view===n[0]?' active\" aria-current=\"page':'')", "replace",
     "(navActive(n[0])?' active\" aria-current=\"page':'')"),
    ("sidebar: open-task badge moves with the slot",
     "if(k==='home'){const n=S.actions", "replace", "if(k==='today'){const n=S.actions"),
    ("top bar: hide Daily standup on Today only",
     "{LT}button class=\"btn btn-sm\" data-act=\"standup\"{GT}'+tx('Daily standup')+'{LT}/button{GT}{LT}/div{GT}';",
     "replace",
     "'+(view==='today'?'':'{LT}button class=\"btn btn-sm\" data-act=\"standup\"{GT}'+tx('Daily standup')+'{LT}/button{GT}')+'{LT}/div{GT}';"),
    ("refreshAccount: re-render Today when account data arrives",
     "['home','dashboard','journey','settings'].includes(view)", "replace",
     "['home','today','dashboard','journey','settings'].includes(view)"),
    ("settings: Show full Command Center by default",
     "{LT}button class=\"btn\" data-act=\"onboard\"{GT}Review coach setup{LT}/button{GT}", "after",
     SETTINGS_TOGGLE),
    ("Arabic strings for Today",
     "'Daily standup':'المراجعة اليومية'};", "replace", AR_STRINGS),
]

POST_CHECKS = [
    "V.today={title:'Today'", "v=todayHomeDefault();", "if(v==='today'){if(first||changed)track('today_viewed'",
    "if(via)m.via=via;", "via:evTakeVia()});", "const NAV=[['today','Today','home'],", "todayHref()",
    "navActive(n[0])", "if(k==='today')", "(view==='today'?'':", "['home','today','dashboard'",
    "data-k=\"ui.homeFull\"", "\"Today's move\":",
]
GONE = [
    "if(v==='home'){if(first||changed)track('today_viewed'", "['home','Command Center','home']",
    "if(!V[v])v='home';",
]


def fail(msg):
    print("ABORTED - nothing was written.")
    print("Reason: " + msg)
    sys.exit(1)


def main():
    if "--sql" in sys.argv:
        print(SQL)
        return
    check_only = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = Path(args[0]) if args else Path("/root/e5-ai-coach/chat_test.html")
    backup = target.with_name(target.name + ".bak-brick2")
    if not target.is_file():
        fail("file not found: " + str(target))

    escaped = (AMP + "gt;", AMP + "lt;", AMP + "amp;")
    for name, anchor, mode, text in PATCHES:
        for bad in (LT, GT, AMP):
            if bad in anchor or bad in text:
                fail("patch '" + name + "' contains a raw forbidden character (copy damage?)")
        for e in escaped:
            if e in anchor or e in text:
                fail("patch '" + name + "' contains HTML-escaped text (copy damage?)")

    src = target.read_text(encoding="utf-8")
    if MARKER in src:
        fail("Brick 2 marker found - this file is already patched.")
    if NEED_1A not in src:
        fail("Brick 1A is not applied to this file. Apply patch_brick1a.py first.")

    problems = []
    for name, anchor, mode, text in PATCHES:
        n = src.count(A(anchor))
        print("  [" + ("OK" if n == 1 else "FOUND " + str(n) + "x") + "] " + name)
        if n != 1:
            problems.append(name)
    if problems:
        fail("anchors missing or not unique: " + ", ".join(problems))

    if check_only:
        print("CHECK PASSED - all " + str(len(PATCHES)) + " anchors found exactly once. Nothing written.")
        return

    out = src
    for name, anchor, mode, text in PATCHES:
        a, t = A(anchor), A(text)
        if mode == "before":
            new = t + a
        elif mode == "after":
            new = a + t
        else:
            new = t
        out = out.replace(a, new, 1)

    if out.count(MARKER) != 1:
        fail("post-check: marker count is wrong")
    for needle in POST_CHECKS:
        if needle not in out:
            fail("post-check: missing " + needle)
    for needle in GONE:
        if needle in out:
            fail("post-check: old code survived: " + needle)

    shutil.copy2(target, backup)
    tmp = target.with_name(target.name + ".tmp-brick2")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, target)
    print("PATCHED: " + str(target) + "  (+" + str(len(out) - len(src)) + " bytes, " + str(len(PATCHES)) + " edits)")
    print("Backup:  " + str(backup))
    print("Rollback: cp " + str(backup) + " " + str(target) + "   then rebuild the container")


main()
