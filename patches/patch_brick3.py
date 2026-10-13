#!/usr/bin/env python3
"""
BRICK 3 - Sidebar 10 items to 4 (Today, Coach, Progress, Tools). Patches chat_test.html only.
Nothing is deleted: Funnel, Content, Community, DM Copilot and Library open from the new
Tools launcher; Settings moves to the sidebar footer (desktop) and the Tools screen (all sizes);
Dashboard merges into Progress (#dashboard redirects to #journey, V.dashboard stays in code).
Requires Brick 2 (and therefore Brick 1A). Works with Brick 1B applied.

Usage:
  python3 patch_brick3.py --check          dry run: verify every anchor, writes nothing
  python3 patch_brick3.py                  patch /root/e5-ai-coach/chat_test.html
  python3 patch_brick3.py /path/file.html  patch another copy
  python3 patch_brick3.py --sql            print the Tools-launcher usage query

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
MARKER = "BRICK 3: Tools launcher"
NEED_2 = "BRICK 2: Today screen"


def A(s):
    """Rebuild placeholders: {LT} and {GT} become the real characters."""
    return s.replace("{LT}", LT).replace("{GT}", GT)


SQL = """-- Brick 3 metric: which tools people open, and how they got there. Run in Supabase.
-- IMPORTANT: replace 2026-10-09 20:00+00 with your Brick 3 deploy time (UTC).
SELECT jsonb_extract_path_text(meta, 'tool') AS tool,
       COALESCE(jsonb_extract_path_text(meta, 'via'), 'sidebar/direct') AS via,
       COUNT(*) AS opens,
       COUNT(DISTINCT member_id) AS members
FROM events
WHERE event_type = 'tool_opened'
  AND created_at BETWEEN TIMESTAMPTZ '2026-10-09 20:00+00' AND NOW()
GROUP BY 1, 2
ORDER BY opens DESC;

-- Launcher conversion: Tools screen views followed within 2 minutes by a tool opened from it.
WITH t AS (
  SELECT id, member_id, created_at FROM events
  WHERE event_type = 'tool_opened'
    AND jsonb_extract_path_text(meta, 'tool') = 'tools'
    AND created_at BETWEEN TIMESTAMPTZ '2026-10-09 20:00+00' AND NOW()
)
SELECT COUNT(*) AS tools_views,
       COUNT(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM events e
         WHERE e.member_id = t.member_id
           AND e.event_type = 'tool_opened'
           AND jsonb_extract_path_text(e.meta, 'via') = 'tools'
           AND e.created_at BETWEEN t.created_at AND t.created_at + INTERVAL '2 minutes'
       )) AS views_with_open
FROM t;
"""

GRID_ICON = (
    "  grid:'{LT}rect x=\"3\" y=\"3\" width=\"7\" height=\"7\" rx=\"1.5\"/{GT}"
    "{LT}rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"1.5\"/{GT}"
    "{LT}rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"1.5\"/{GT}"
    "{LT}rect x=\"14\" y=\"14\" width=\"7\" height=\"7\" rx=\"1.5\"/{GT}',\n"
)

TOOLS_JS = r"""
// ===== BRICK 3: Tools launcher (sidebar 10 to 4; every tool stays one click away) =====
const TOOL_TILES=[
 ['funnel','Funnel','funnel','Revenue math, launch planner and reality check.'],
 ['content','Content','pen','A 7-day content plan built from your Business DNA.'],
 ['community','Community','users','Seven tools to grow engagement and sales in your community.'],
 ['dm','DM Copilot','chat','Track conversations and draft the next follow-up.'],
 ['library','Library','book','Every AI answer you saved.']
];
// Real one-line status only; empty string hides the line (Rule 5).
function toolStatus(id){
 try{
  if(id==='funnel'){const g=num((S.funnel||{}).goal);return g?tx('Revenue goal')+': '+money(g):'';}
  if(id==='content'){const p=Array.isArray((S.content||{}).plan)?S.content.plan:[];if(!p.length)return '';return 'Plan: '+p.filter(function(x){return x.done;}).length+' of '+p.length+' posts published';}
  if(id==='community'){const a=((S.community||{}).inputs||{}).audit||{};const m=num(a.members);return m?int(m)+' members':'';}
  if(id==='dm'){const n=leadStats().overdue;return n?plural(n,'follow-up')+' due':'';}
  if(id==='library'){const n=S.library.length;return n?plural(n,'saved answer'):'';}
 }catch(e){}
 return '';
}
function toolArrow(){return S.ui.lang==='ar'?' ←':' →';}
function toolTile(t){
 const st=toolStatus(t[0]);
 return '{LT}div class="card"{GT}{LT}h3 class="row"{GT}'+ic(t[2],18)+'{LT}span{GT}'+esc(tx(t[1]))+'{LT}/span{GT}{LT}/h3{GT}'
  +'{LT}p class="muted mt-s"{GT}'+esc(tx(t[3]))+'{LT}/p{GT}'
  +(st?'{LT}p class="hint mt-s"{GT}'+esc(st)+'{LT}/p{GT}':'')
  +'{LT}div class="row mt"{GT}{LT}a class="btn btn-sm" href="#'+t[0]+'" data-via="tools"{GT}'+esc(tx('Open'))+toolArrow()+'{LT}/a{GT}{LT}/div{GT}{LT}/div{GT}';
}
V.tools={title:'Tools',sub:'Every growth tool in one place. Open one when you need it.',render:function(){
 return '{LT}div class="grid-2"{GT}'+TOOL_TILES.map(toolTile).join('')+'{LT}/div{GT}'
  +'{LT}div class="row mt"{GT}{LT}a class="btn btn-ghost btn-sm" href="#settings" data-via="tools"{GT}'+esc(tx('Settings'))+toolArrow()+'{LT}/a{GT}{LT}/div{GT}';
}};
// ===== end BRICK 3 core =====
"""

NAV_ACTIVE_NEW = (
    "function navActive(k){"
    "if(k==='today')return view==='today'||view==='home';"
    "if(k==='journey')return view==='journey'||view==='dashboard';"
    "if(k==='tools')return ['tools','funnel','content','community','dm','library'].indexOf(view)!==-1;"
    "return view===k;}"
)

SETTINGS_FOOT = (
    "{LT}a href=\"#settings\" class=\"nav-item'+(view==='settings'?' active\" aria-current=\"page':'')"
    "+'\" title=\"'+esc(tx('Settings'))+'\"{GT}'+ic('save')+'{LT}span{GT}'+esc(tx('Settings'))+'{LT}/span{GT}{LT}/a{GT}"
)

AR_STRINGS = (
    "'Save and continue':'احفظ وتابع',"
    "'Coach':'المدرب','Progress':'التقدم','Tools':'الأدوات','Open':'افتح','Revenue goal':'هدف الإيرادات',"
    "'Revenue math, launch planner and reality check.':'حسابات الإيرادات، مخطط الإطلاق، وفحص الواقع.',"
    "'A 7-day content plan built from your Business DNA.':'خطة محتوى لسبعة أيام مبنية على هوية مشروعك.',"
    "'Seven tools to grow engagement and sales in your community.':'سبع أدوات لزيادة التفاعل والمبيعات في مجتمعك.',"
    "'Track conversations and draft the next follow-up.':'تابع المحادثات واكتب رسالة المتابعة التالية.',"
    "'Every AI answer you saved.':'كل إجابات الذكاء الاصطناعي التي حفظتها.'};"
)

# (name, anchor, mode, text) - raw, placeholders rebuilt by A() at runtime.  mode: before | after | replace
PATCHES = [
    ("icon: add grid icon for Tools",
     "const ICON={\n", "after", GRID_ICON),
    ("core: Tools launcher view and tile status lines",
     "// ===== end BRICK 2 core =====", "after", TOOLS_JS),
    ("sidebar: 4 items (Today, Coach, Progress, Tools)",
     "const NAV=[['today','Today','home'],['dashboard','Dashboard','bolt'],['chat','AI Coach','spark'],"
     "['journey','My Journey','list'],['funnel','Funnel','funnel'],['content','Content','pen'],"
     "['community','Community','users'],['dm','DM Copilot','chat'],['library','Library','book'],"
     "['settings','Settings','save']];",
     "replace",
     "const NAV=[['today','Today','home'],['chat','Coach','spark'],['journey','Progress','list'],['tools','Tools','grid']];"),
    ("sidebar: remove WORKSPACE / GROWTH TOOLS / YOUR RESOURCES headers",
     "([0,4,8].includes(i)?'{LT}span class=\"nav-group\"{GT}'+['WORKSPACE','GROWTH TOOLS','YOUR RESOURCES']"
     "[[0,4,8].indexOf(i)]+'{LT}/span{GT}':'')+",
     "replace", ""),
    ("sidebar: Settings in the footer (icon only when collapsed)",
     "{LT}div class=\"side-foot nav\"{GT}", "after", SETTINGS_FOOT),
    ("sidebar: overdue follow-ups badge moves to Tools",
     "if(k==='dm'){const n=leadStats().overdue;", "replace", "if(k==='tools'){const n=leadStats().overdue;"),
    ("sidebar: highlighting (Progress covers Dashboard, Tools covers every tool)",
     "function navActive(k){if(k==='today')return view==='today'||view==='home';return view===k;}",
     "replace", NAV_ACTIVE_NEW),
    ("route: #coach, #progress aliases; #dashboard redirects to #journey",
     "if(h==='command'||h==='main')v='home';if(h==='ai-coach')v='chat';", "replace",
     "if(h==='command'||h==='main')v='home';if(h==='ai-coach'||h==='coach')v='chat';if(h==='progress')v='journey';"
     "if(h==='dashboard'){v='journey';try{history.replaceState(null,'','#journey');}catch(e){}}"),
    ("title: AI Coach becomes Coach",
     "V.chat={title:'AI Coach',", "replace", "V.chat={title:'Coach',"),
    ("title: My Journey becomes Progress",
     "V.journey={title:'My Journey',", "replace", "V.journey={title:'Progress',"),
    ("Progress: recent activity and wins merged in from Dashboard",
     "Refresh progress{LT}/button{GT}{LT}/div{GT}\n ${ps.length", "replace",
     "Refresh progress{LT}/button{GT}{LT}/div{GT}{LT}div class=\"mt\"{GT}${activityHTML()}{LT}/div{GT}\n ${ps.length"),
    ("refreshAccount: re-render Tools when account data arrives",
     "['home','today','dashboard','journey','settings'].includes(view)", "replace",
     "['home','today','dashboard','journey','settings','tools'].includes(view)"),
    ("Arabic strings for the new labels and tiles",
     "'Save and continue':'احفظ وتابع'};", "replace", AR_STRINGS),
]

POST_CHECKS = [
    "V.tools={title:'Tools'", "['tools','Tools','grid']", "grid:'", "href=\"#settings\" class=\"nav-item",
    "if(k==='tools'){const n=leadStats().overdue;", "if(k==='journey')return view==='journey'||view==='dashboard';",
    "if(h==='progress')v='journey';", "V.chat={title:'Coach',", "V.journey={title:'Progress',",
    "${activityHTML()}", "'settings','tools'].includes(view)", "'Tools':'الأدوات'",
]
GONE = [
    "'WORKSPACE','GROWTH TOOLS'", "V.chat={title:'AI Coach',", "V.journey={title:'My Journey',",
    "['dashboard','Dashboard','bolt']", "if(k==='dm'){const n=leadStats().overdue;",
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
    backup = target.with_name(target.name + ".bak-brick3")
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
        fail("Brick 3 marker found - this file is already patched.")
    if NEED_2 not in src:
        fail("Brick 2 is not applied to this file. Apply patch_brick2.py first.")

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
    tmp = target.with_name(target.name + ".tmp-brick3")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, target)
    print("PATCHED: " + str(target) + "  (+" + str(len(out) - len(src)) + " bytes, " + str(len(PATCHES)) + " edits)")
    print("Backup:  " + str(backup))
    print("Rollback: cp " + str(backup) + " " + str(target) + "   then rebuild the container")


main()
