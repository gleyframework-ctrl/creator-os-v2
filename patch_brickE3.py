#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_brickE3.py  --  Brick E3 (fair standup) + Bug 1 (comma decimals), one patch for two files

main.py
  - Standup grading matches the task. Link (+2) and Metrics (+2) only count when the
    task asks for them. Tasks like p1_t2 (avatar, fears) grade Deliverables 0-4 plus
    Quality 0-6, so 10/10 is reachable. Pass threshold stays at 7.
  - The STRICT COO prompt is replaced by a plain-language grader: no framework names,
    one REASON, one HINT, one NEXT. Any framework name that slips through is swapped
    for a plain fallback sentence. The server adds the link and number points itself.
  - /api/standup also returns reason, hint, next_step, rubric. /api/journey returns
    standup_rubric for the current task. Nothing else changes (XP, streak, day, DB).

chat_test.html
  - Standup form: guided users have no 100-character minimum, deliverable ticks are
    optional unless the task needs them, link and number fields say needed or optional.
  - Failed standup: score, one reason, one hint, and a Try again button. The text,
    links, numbers, ticks and attached files are kept (also kept if the page reloads).
  - Bug 1: parseNum(). "0,4" is 0.4 and "2,5" is 2.5 in every % field, price field and
    Unsub %. A lone comma is never a thousands separator. Arabic digits work too.
  - Not included: raw br and ** rendering (Brick F).

Usage (in /root/e5-ai-coach/):
    python3 patch_brickE3.py --check     # dry run, writes nothing
    python3 patch_brickE3.py             # apply, with backups
    python3 patch_brickE3.py --dir PATH  # files in another folder

Refuses when: BRICK E1 is missing, BRICK E3 is already there, or any anchor is not found
exactly once. Then nothing is written.

Rollback:
    cp main.py.bak-brickE3 main.py
    cp chat_test.html.bak-brickE3 chat_test.html
"""
import os, sys, shutil, subprocess, tempfile, py_compile, operator as op

LT, GT, AMP = chr(60), chr(62), chr(38)


def u(s):
    return s.replace('@LT@', LT).replace('@GT@', GT).replace('@AMP@', AMP)


MARK = 'BRICK E3'
NEED = 'BRICK E1'
BAK = '.bak-brickE3'

MAIN_EDITS = [
    ('standup helpers: task rubric, plain grader, jargon filter',
     '# --- STANDUP ---\n@app.post("/api/standup")',
     '# ===== BRICK E3: fair standup. Grading matches the task. Plain-language grader. =====\n# Link (+2) and Numbers (+2) are scored by the server, and only when the task asks for them.\n# The AI scores the rest (parts covered + quality). Total is always out of 10. Pass stays at 7.\n# (needs_link, needs_numbers) per task. Unknown task ids fall back to the deliverables text.\n# A task dict can override with "standup_link", "standup_metrics", "standup_checks".\n_E3_NEEDS = {\n    "p1_t1": (False, False), "p1_t2": (False, False), "p1_t3": (True, True), "p1_t4": (False, True),\n    "p2_t1": (True, True), "p2_t2": (False, False), "p2_t3": (False, True), "p2_t4": (False, True),\n    "p3_t1": (True, False), "p3_t2": (False, False), "p3_t3": (False, True), "p3_t4": (False, True),\n}\n_E3_JARGON_CAPS = ["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S"]\n_E3_JARGON_NAMES = ["Hormozi", "Kallaway", "Cattoni", "Tutton", "Belcher", "Rohan", "Value Equation",\n                    "Pain Stack", "Tiny Yeses", "DM Doctor", "Offer Architect", "Community OS",\n                    "Content Engine", "Dream Customer", "Dream Follower", "Hook Mastery", "Anti-viral",\n                    "Launch Planner", "21-day launch map", "Customer Value Journey"]\n\n\ndef _e3_rubric(task):\n    task = task if isinstance(task, dict) else {}\n    tid = str(task.get("id", ""))\n    if tid in _E3_NEEDS:\n        link, numbers = _E3_NEEDS[tid]\n    else:\n        text = " ".join(str(d) for d in task.get("deliverables", [])).lower()\n        link = any(w in text for w in ("link", "url"))\n        numbers = any(w in text for w in ("count", "rate", "revenue", "views", "reported", "before and after", "tracker", "%"))\n    link = bool(task.get("standup_link", link))\n    numbers = bool(task.get("standup_metrics", numbers))\n    checks = bool(task.get("standup_checks", False))\n    ai_max = 10 - (2 if link else 0) - (2 if numbers else 0)\n    parts = 2 + (0 if link else 1) + (0 if numbers else 1)\n    return {"task_id": tid, "link": link, "metrics": numbers, "checks": checks,\n            "parts_max": parts, "quality_max": ai_max - parts, "ai_max": ai_max}\n\n\ndef _e3_has_link(links):\n    for x in links or []:\n        s = str(x or "").strip().lower()\n        if s.startswith("http://") or s.startswith("https://") or s.startswith("/api/proof/"):\n            return True\n    return False\n\n\ndef _e3_has_numbers(metrics):\n    return bool(re.search(r"\\d", str(metrics or "")))\n\n\ndef _e3_has_jargon(s):\n    s = str(s or "")\n    caps = r"\\b(" + "|".join(re.escape(w) for w in _E3_JARGON_CAPS) + r")\\b"\n    names = r"(?i)\\b(" + "|".join(re.escape(w) for w in _E3_JARGON_NAMES) + r")\\b"\n    return bool(re.search(caps, s) or re.search(names, s))\n\n\ndef _e3_grader_prompt(task, profile, rubric, link_ok, numbers_ok):\n    N = chr(10)\n    parts = N.join("- " + str(d) for d in task.get("deliverables", [])) or "- (no list given)"\n    lines = [\n        "You check a beginner\'s work on one task in a business coaching app. Be fair, kind and honest.",\n        "",\n        "TASK: " + str(task.get("name", "")),\n        "WHY IT MATTERS: " + str(task.get("why", "")),\n        "THE PARTS OF THIS TASK:", parts,\n        "MEMBER: niche = " + str(profile.get("niche", "N/A")) + ", customer = " + str(profile.get("target_avatar", "N/A")),\n        "",\n        "Score only two things:",\n        "1. PARTS (0-" + str(rubric["parts_max"]) + "): how much of the list above is clearly in the work. Short, simple answers count. If a part is a link or a number, skip it: the app checks those itself.",\n        "2. QUALITY (0-" + str(rubric["quality_max"]) + "): is it specific to their business and their customer, and could they really use it?",\n        "Add the two. Never take points off for missing links or numbers, and never for spelling, grammar or language.",\n    ]\n    if rubric["link"]:\n        lines.append("Note: this task needs a link. Link given: " + ("yes" if link_ok else "no") + ".")\n    if rubric["metrics"]:\n        lines.append("Note: this task needs numbers. Numbers given: " + ("yes" if numbers_ok else "no") + ".")\n    lines += [\n        "",\n        "Rules: plain everyday words, like a kind friend. No jargon, no acronyms, no framework names, no author or book names. Do not invent anything about their work. Write REASON, HINT and NEXT in the same language as the member\'s work.",\n        "",\n        "OUTPUT exactly these 4 lines and nothing else:",\n        "GRADE: X/" + str(rubric["ai_max"]),\n        "REASON: one short sentence, the main reason for this score",\n        "HINT: one short sentence, the single most useful thing to add or fix",\n        "NEXT: one short sentence, what to do once this task is done",\n    ]\n    return N.join(lines)\n\n\ndef _e3_parse_grade(raw, ai_max):\n    m = re.search(r"GRADE:\\s*(\\d+)(?:\\s*/\\s*(\\d+))?", str(raw or ""))\n    if not m:\n        return 0\n    x = int(m.group(1))\n    if m.group(2):\n        den = int(m.group(2))\n    else:\n        den = ai_max if x @LT@= ai_max else 10\n    if den @GT@ 0 and den != ai_max:\n        x = int(round(x * ai_max / float(den)))\n    return min(ai_max, max(0, x))\n\n\ndef _e3_line(raw, key):\n    m = re.search(r"(?im)^[\\s*#_-]*" + key + r"[\\s*_]*:[\\s*_]*(.+)$", str(raw or ""))\n    if not m:\n        return ""\n    s = re.sub(r"(?i)@LT@br\\s*/?@GT@", " ", m.group(1))\n    s = re.sub(r"[*_`#]+", "", s).strip()\n    return s[:300]\n\n\ndef _e3_feedback(raw, score, rubric, link_ok, numbers_ok):\n    passed = score @GT@= 7\n    reason, hint, nxt = _e3_line(raw, "REASON"), _e3_line(raw, "HINT"), _e3_line(raw, "NEXT")\n    if not reason or _e3_has_jargon(reason):\n        reason = "Your work covers what this task asks for." if passed else "Some parts of this task are still missing or too general."\n    if not passed and rubric["link"] and not link_ok:\n        hint = "Add the link to your work. It must start with http:// or https://"\n    elif not passed and rubric["metrics"] and not numbers_ok:\n        hint = "Add your real numbers, for example views, replies or sales."\n    elif not hint or _e3_has_jargon(hint):\n        hint = "Pick the part of the list you skipped and add it in a few clear lines."\n    if not nxt or _e3_has_jargon(nxt):\n        nxt = "Open your next task and start with the first part."\n    return reason, hint, nxt\n\n\ndef _e3_review_text(score, reason, hint, nxt):\n    N = chr(10)\n    out = "GRADE: " + str(score) + "/10" + N + N + "REASON: " + reason + N + N\n    return out + ("NEXT: " + nxt if score @GT@= 7 else "HINT: " + hint)\n\n\n# --- STANDUP ---\n@app.post("/api/standup")',
     1),
    ('submit_standup: STRICT COO replaced by task-matched plain grader',
     '    frameworks_str = ", ".join(task.get("frameworks", []))\n    deliverables_str = "\\n".join([f"- {d}" for d in task.get("deliverables", [])])\n    system = f"""You are a STRICT COO grading execution.\nTASK: {task[\'name\']}\nFRAMEWORKS: {frameworks_str}\nDELIVERABLES:\\n{deliverables_str}\nMEMBER: Niche={profile.get(\'niche\',\'N/A\')} | Speed={profile.get(\'speed_profile\',\'steady\')} | Traffic Source={profile.get(\'primary_traffic_source\',\'content\')}\nRUBRIC: Link(+2), Metrics(+2), Deliverables(+2), Quality(0-4).\nOUTPUT: GRADE: [X]/10\nAUDIT: [2-3 issues]\nWHAT TO FIX: [if @LT@7]\nNEXT STEP: [if @GT@=7]\nFRAMEWORK TIP: [insight]"""\n    prompt = f"Tasks: {req.tasks_completed}\\nLinks: {req.asset_links}\\nContent: {req.asset_text}\\nMetrics: {req.metrics}"\n    review = llm_result(call_llm([{"role":"system","content":system},{"role":"user","content":prompt}]))\n    if not re.search(r\'GRADE:\\s*\\d+\', review): raise HTTPException(502, "AI review did not include a valid grade.")\n    score = 5\n    try: m = re.search(r\'GRADE:\\s*(\\d+)\', review); score = int(m.group(1)) if m else 5\n    except: pass\n    score = min(10, max(0, score))\n',
     '    # BRICK E3: grading matches the task. The server scores link and numbers, the AI scores the rest.\n    rubric = _e3_rubric(task)\n    link_ok = _e3_has_link(req.asset_links)\n    numbers_ok = _e3_has_numbers(req.metrics)\n    system = _e3_grader_prompt(task, profile, rubric, link_ok, numbers_ok)\n    prompt = "Completed actions: " + "; ".join(str(x) for x in req.tasks_completed) + "\\nLinks: " + ", ".join(str(x) for x in req.asset_links) + "\\nWork: " + str(req.asset_text) + "\\nNumbers: " + str(req.metrics)\n    raw_review = llm_result(call_llm([{"role":"system","content":system},{"role":"user","content":prompt}]))\n    if not re.search(r\'GRADE:\\s*\\d+\', str(raw_review)): raise HTTPException(502, "AI review did not include a valid grade.")\n    ai_score = _e3_parse_grade(raw_review, rubric["ai_max"])\n    link_pts = 2 if (rubric["link"] and link_ok) else 0\n    number_pts = 2 if (rubric["metrics"] and numbers_ok) else 0\n    score = min(10, max(0, ai_score + link_pts + number_pts))\n    e3_reason, e3_hint, e3_next = _e3_feedback(raw_review, score, rubric, link_ok, numbers_ok)\n    review = _e3_review_text(score, e3_reason, e3_hint, e3_next)\n',
     1),
    ('submit_standup: response adds reason, hint, next_step, rubric',
     '    return {"success": True, "review": review, "score": score, "task_unlocked": score @GT@= 7, "streak": journey.get("streak",0), "xp_gained": xp_gained, "xp_total": journey.get("xp_total",0), "journey_updated": True}',
     '    return {"success": True, "review": review, "score": score, "task_unlocked": score @GT@= 7, "streak": journey.get("streak",0), "xp_gained": xp_gained, "xp_total": journey.get("xp_total",0), "journey_updated": True, "reason": e3_reason, "hint": e3_hint, "next_step": e3_next, "rubric": rubric, "points": {"ai": ai_score, "link": link_pts, "numbers": number_pts}}  # BRICK E3',
     1),
    ('journey: standup_rubric for the current task',
     '        "current_task": current_task,\n',
     '        "current_task": current_task,\n        "standup_rubric": _e3_rubric(current_task) if isinstance(current_task, dict) else None,  # BRICK E3\n',
     1),
]

HTML_EDITS = [
    ('Bug 1: parseNum helper, num() routed through it',
     "const num=v=@GT@{const n=typeof v==='number'?v:parseFloat(String(v==null?'':v).replace(/,/g,''));return Number.isFinite(n)?n:0;};",
     "// ===== BRICK E3: parseNum. One comma or one dot is the decimal mark (0,4 = 0.4). Commas are never stripped as thousands. Arabic digits work. =====\nconst parseNum=v=@GT@{if(typeof v==='number')return Number.isFinite(v)?v:NaN;let s=String(v==null?'':v).trim();if(!s)return NaN;s=s.replace(/[\\u0660-\\u0669]/g,d=@GT@String(d.charCodeAt(0)-1632)).replace(/[\\u06F0-\\u06F9]/g,d=@GT@String(d.charCodeAt(0)-1776)).replace(/\\u066B/g,'.').replace(/\\u060C/g,',').replace(/[\\s\\u00a0\\u202f\\u066C]/g,'').replace(/[$%\\u20ac\\u00a3]/g,'');const c=(s.match(/,/g)||[]).length,p=(s.match(/\\./g)||[]).length;if(c+p@GT@1)return NaN;if(c===1)s=s.replace(',','.');const n=parseFloat(s);return Number.isFinite(n)?n:NaN;};\nconst num=v=@GT@{const n=parseNum(v);return Number.isFinite(n)?n:0;};",
     1),
    ('Bug 1: readVal() reads decimal text fields through num()',
     "function readVal(el){if(el.type==='number')return",
     "function readVal(el){if(el.type==='number'||(el.dataset@AMP@@AMP@el.dataset.num!==undefined))return",
     1),
    ('Bug 1: fld() number fields become decimal text fields',
     'type="${o.type||\'text\'}"${o.type===\'number\'?\' inputmode="decimal" step="any"\':\'\'}',
     'type="${o.type===\'number\'?\'text\':(o.type||\'text\')}"${o.type===\'number\'?\' inputmode="decimal" data-num="1" autocomplete="off"\':\'\'}',
     1),
    ('Bug 1: inputField() number fields become decimal text fields',
     'type="${options.type||\'text\'}" value="${esc(value)}"${options.type===\'number\'?\' min="0" step="any"\':\'\'}',
     'type="${options.type===\'number\'?\'text\':(options.type||\'text\')}" value="${esc(value)}"${options.type===\'number\'?\' inputmode="decimal" data-num="1" autocomplete="off"\':\'\'}',
     1),
    ('Bug 1: funnel, tracker and format-value inputs (3x) become decimal text fields',
     'type="number" step="any" inputmode="decimal"',
     'type="text" inputmode="decimal" data-num="1" autocomplete="off"',
     3),
    ('E3: standup form, grading result, Try again',
     'function standupModal(){\n const t=S.main.journey?.current_task;if(!t){toast(\'Connect your account and load your current journey task first.\');return;}\n modalForm(\'Daily standup — \'+t.name,`@LT@p class="muted"@GT@Explain what you built. Grading and task unlocks are confirmed by your server.@LT@/p@GT@@LT@div class="standup-checks"@GT@${(t.deliverables||[]).map((d,i)=@GT@`@LT@label class="row"@GT@@LT@input type="checkbox" class="deliverable-check"@GT@ ${esc(d)}@LT@/label@GT@`).join(\'\')}@LT@/div@GT@\n ${inputField(\'Your work (minimum 100 characters)\',\'standupText\',\'\',{area:true,max:20000})}@LT@div id="standupCounter" class="hint"@GT@0 characters · minimum 100@LT@/div@GT@@LT@div class="form-grid mt"@GT@${inputField(\'Completed actions (one per line)\',\'standupTasks\',\'\',{area:true})}${inputField(\'Evidence links (one per line)\',\'standupLinks\',\'\',{area:true})}@LT@/div@GT@${inputField(\'Metrics / results\',\'standupMetrics\',\'\',{area:true})}${proofUI(\'standup\')}`,`@LT@button class="btn" data-act="modal-close"@GT@Cancel@LT@/button@GT@@LT@button class="btn btn-primary" data-act="submit-standup"@GT@Submit for review@LT@/button@GT@`);\n}\nACT.standup=standupModal;\nACT[\'submit-standup\']=el=@GT@busy(el,async()=@GT@{\n const text=val(\'standupText\');if(text.length@LT@100)throw new Error(\'Add at least 100 characters explaining your work.\');\n if($$(\'.deliverable-check\').some(x=@GT@!x.checked))throw new Error(\'Confirm every deliverable before submitting.\');\n const links=val(\'standupLinks\').split(\'\\n\').map(x=@GT@x.trim()).filter(Boolean);if(links.some(x=@GT@!safeURL(x)))throw new Error(\'Evidence links must be complete http or https URLs.\');track(\'task_submitted\',{task_id:String(S.main.journey?.current_task?.id||\'\'),char_count:text.length});\n const t=S.main.journey?.current_task,files=await proofPayload(),d=await postJSON(\'/api/standup\',{member_id:memberId(),current_task_id:t.id,tasks_completed:val(\'standupTasks\').split(\'\\n\').filter(Boolean),asset_links:[...links,...files.map(f=@GT@f.url)],asset_text:text,metrics:val(\'standupMetrics\'),proof_files:files},150000);\n if(d.error||d.ok===false)throw new Error(d.error||\'Submission failed.\');\n if(d.score==null)throw new Error(\'The server did not confirm a review score.\');track(d.task_unlocked?\'task_passed\':\'task_failed\',{task_id:String(t.id),score:num(d.score)});\n addActivity(`Standup reviewed: ${t.name} — ${d.score}/10`);proofFiles=[];\n await refreshAccount(true);\n modalForm(d.task_unlocked?\'Task complete — \'+t.name:\'Your standup review\',`@LT@div class="review-score"@GT@${esc(d.score)}@LT@span class="hint"@GT@/10@LT@/span@GT@@LT@/div@GT@@LT@div class="md"@GT@${md(d.review||\'Review received.\')}@LT@/div@GT@@LT@p class="hint"@GT@${int(d.xp_gained||0)} XP earned · ${int(d.streak||0)} day streak@LT@/p@GT@${proofReceiptHTML(files)}`,`@LT@button class="btn btn-primary" data-act="modal-close"@GT@Continue@LT@/button@GT@`);\n if(d.task_unlocked@AMP@@AMP@num(d.score)@GT@=7)celebrate();\n});\n',
     '// ===== BRICK E3: fair standup. Form matches the task, plain feedback, Try again keeps your work. =====\nconst E3={draft:null,files:[]};\nfunction e3Key(t){return \'cos_e3_standup_\'+String(t@AMP@@AMP@t.id||\'\');}\nfunction e3Rubric(t){const r=S.main.journey@AMP@@AMP@S.main.journey.standup_rubric;const ok=!!(r@AMP@@AMP@typeof r===\'object\'@AMP@@AMP@String(r.task_id||\'\')===String(t.id));return {link:!!(ok@AMP@@AMP@r.link),metrics:!!(ok@AMP@@AMP@r.metrics),checks:!!(ok@AMP@@AMP@r.checks)};}\nfunction e3Blank(t){return {id:String(t.id),text:\'\',tasks:\'\',links:\'\',metrics:\'\',checks:[]};}\nfunction e3ReadDraft(t){if(E3.draft@AMP@@AMP@E3.draft.id===String(t.id))return E3.draft;try{const d=JSON.parse(localStorage.getItem(e3Key(t))||\'null\');if(d@AMP@@AMP@typeof d===\'object\'@AMP@@AMP@!Array.isArray(d))return Object.assign(e3Blank(t),d,{id:String(t.id)});}catch(e){}return e3Blank(t);}\nfunction e3SaveDraft(){const t=S.main.journey@AMP@@AMP@S.main.journey.current_task;const box=$(\'#standupText\');if(!t||!box)return;const g=id=@GT@{const x=$(\'#\'+id);return x?String(x.value||\'\'):\'\';};const d={id:String(t.id),text:String(box.value||\'\'),tasks:g(\'standupTasks\'),links:g(\'standupLinks\'),metrics:g(\'standupMetrics\'),checks:$$(\'.deliverable-check\').map(x=@GT@!!x.checked)};E3.draft=d;try{localStorage.setItem(e3Key(t),JSON.stringify(d));}catch(e){}}\nfunction e3ClearDraft(t){E3.draft=null;E3.files=[];try{localStorage.removeItem(e3Key(t));}catch(e){}}\nfunction e3CounterText(n){if(guidedOn())return n?n+\' characters\':\'A few clear lines are enough.\';return n+\' characters · \'+(n@LT@100?(100-n)+\' more needed\':\'ready to submit\');}\nfunction e3Plain(s){return String(s==null?\'\':s).replace(/\\*\\*|__|`/g,\'\').trim();}\nfunction standupModal(){\n const t=S.main.journey?.current_task;if(!t){toast(\'Connect your account and load your current journey task first.\');return;}\n const r=e3Rubric(t),d=e3ReadDraft(t),g=guidedOn(),need=x=@GT@x?\' (needed for this task)\':\' (optional)\';\n const checks=(t.deliverables||[]).map((x,i)=@GT@`@LT@label class="row"@GT@@LT@input type="checkbox" class="deliverable-check"${d.checks@AMP@@AMP@d.checks[i]?\' checked\':\'\'}@GT@ ${esc(x)}@LT@/label@GT@`).join(\'\');\n modalForm(\'Daily standup — \'+t.name,`@LT@p class="muted"@GT@${r.checks?\'Tick each part when it is done, then show your work below.\':\'This task covers the parts below. Ticking them is optional.\'}@LT@/p@GT@@LT@div class="standup-checks"@GT@${checks}@LT@/div@GT@\n ${inputField(g?\'What did you do? Write it your way\':\'Your work (minimum 100 characters)\',\'standupText\',d.text||\'\',{area:true,max:20000})}@LT@div id="standupCounter" class="hint"@GT@${esc(e3CounterText(String(d.text||\'\').trim().length))}@LT@/div@GT@@LT@div class="form-grid mt"@GT@${inputField(\'Completed actions (one per line, optional)\',\'standupTasks\',d.tasks||\'\',{area:true})}${inputField(\'Links\'+need(r.link)+\', one per line\',\'standupLinks\',d.links||\'\',{area:true})}@LT@/div@GT@${inputField(\'Numbers / results\'+need(r.metrics),\'standupMetrics\',d.metrics||\'\',{area:true})}${proofUI(\'standup\')}`,`@LT@button class="btn" data-act="modal-close"@GT@Cancel@LT@/button@GT@@LT@button class="btn btn-primary" data-act="submit-standup"@GT@Submit for review@LT@/button@GT@`);\n if(E3.files.length){proofFiles=E3.files.slice();renderProofs();}\n}\nACT.standup=standupModal;\nACT[\'submit-standup\']=el=@GT@busy(el,async()=@GT@{\n const t=S.main.journey?.current_task;if(!t)throw new Error(\'Load your current task first.\');\n const r=e3Rubric(t),text=val(\'standupText\');\n if(guidedOn()){if(!text)throw new Error(\'Write a few words about what you did.\');}\n else if(text.length@LT@100)throw new Error(\'Add at least 100 characters explaining your work.\');\n if(r.checks@AMP@@AMP@$$(\'.deliverable-check\').some(x=@GT@!x.checked))throw new Error(\'Tick every part of this task before submitting.\');\n const links=val(\'standupLinks\').split(\'\\n\').map(x=@GT@x.trim()).filter(Boolean);if(links.some(x=@GT@!safeURL(x)))throw new Error(\'Links must be complete addresses that start with http:// or https://\');\n e3SaveDraft();track(\'task_submitted\',{task_id:String(t.id),char_count:text.length});\n const files=await proofPayload(),d=await postJSON(\'/api/standup\',{member_id:memberId(),current_task_id:t.id,tasks_completed:val(\'standupTasks\').split(\'\\n\').filter(Boolean),asset_links:[...links,...files.map(f=@GT@f.url)],asset_text:text,metrics:val(\'standupMetrics\'),proof_files:files},150000);\n if(d.error||d.ok===false)throw new Error(d.error||\'Submission failed.\');\n if(d.score==null)throw new Error(\'The server did not confirm a review score.\');track(d.task_unlocked?\'task_passed\':\'task_failed\',{task_id:String(t.id),score:num(d.score)});\n addActivity(`Standup reviewed: ${t.name} — ${d.score}/10`);\n if(d.task_unlocked)e3ClearDraft(t);else E3.files=proofFiles.slice();\n proofFiles=[];\n await refreshAccount(true);\n e3ResultModal(t,d,files);\n if(d.task_unlocked@AMP@@AMP@num(d.score)@GT@=7)celebrate();\n});\nfunction e3ResultModal(t,d,files){\n const pass=!!d.task_unlocked,reason=e3Plain(d.reason),hint=e3Plain(d.hint),next=e3Plain(d.next_step);\n const body=(reason||hint||next)?`@LT@p class="mt"@GT@@LT@b@GT@${pass?\'Why it passed\':\'Why this score\'}:@LT@/b@GT@ ${esc(reason)}@LT@/p@GT@${pass?(next?`@LT@p@GT@@LT@b@GT@Next:@LT@/b@GT@ ${esc(next)}@LT@/p@GT@`:\'\'):(hint?`@LT@p class="callout"@GT@@LT@b@GT@Hint:@LT@/b@GT@ ${esc(hint)}@LT@/p@GT@`:\'\')}`:`@LT@div class="md"@GT@${md(d.review||\'Review received.\')}@LT@/div@GT@`;\n const foot=pass?\'7 or more unlocks the next task. Done.\':\'7 or more unlocks the next task. Your text is saved: fix one thing and try again.\';\n const streak=num(d.streak)@GT@0?`@LT@p class="hint"@GT@${int(d.streak)}-day streak@LT@/p@GT@`:\'\';\n modalForm(pass?\'Task complete — \'+t.name:\'Not yet — \'+t.name,`@LT@div class="review-score"@GT@${esc(d.score)}@LT@span class="hint"@GT@/10@LT@/span@GT@@LT@/div@GT@${body}@LT@p class="hint"@GT@${foot}@LT@/p@GT@${streak}${proofReceiptHTML(files)}`,pass?`@LT@button class="btn btn-primary" data-act="modal-close"@GT@Continue@LT@/button@GT@`:`@LT@button class="btn" data-act="modal-close"@GT@Later@LT@/button@GT@@LT@button class="btn btn-primary" data-act="standup-retry"@GT@Try again@LT@/button@GT@`);\n}\nACT[\'standup-retry\']=()=@GT@standupModal();\ndocument.addEventListener(\'input\',e=@GT@{const el=e.target;if(!el)return;if([\'standupText\',\'standupTasks\',\'standupLinks\',\'standupMetrics\'].includes(el.id))e3SaveDraft();if(el.dataset@AMP@@AMP@el.dataset.num!==undefined){const ok=!String(el.value||\'\').trim()||Number.isFinite(parseNum(el.value));el.setAttribute(\'aria-invalid\',ok?\'false\':\'true\');el.title=ok?\'\':\'Use one comma or one dot for decimals, for example 0,4\';el.style.borderColor=ok?\'\':\'#e5484d\';}});\ndocument.addEventListener(\'change\',e=@GT@{const el=e.target;if(el@AMP@@AMP@el.classList@AMP@@AMP@el.classList.contains(\'deliverable-check\'))e3SaveDraft();});\n',
     1),
    ('E3: standup counter text',
     "$('#standupCounter').textContent=n+' characters · '+(n@LT@100?(100-n)+' more needed':'ready to submit');",
     "$('#standupCounter').textContent=e3CounterText(n);",
     1),
]


def fail(msg):
    print('REFUSED: ' + msg)
    print('Nothing was written.')
    sys.exit(1)


def read(p):
    with open(p, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def apply_edits(text, edits, fname):
    for label, old, new, want in edits:
        o, n = u(old), u(new)
        c = text.count(o)
        if op.ne(c, want):
            fail(fname + ': anchor for "' + label + '" found ' + str(c) +
                 ' times (expected exactly ' + str(want) + '). This file differs from the version the patch was tested on.')
        text = text.replace(o, n)
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
    tmp = path + '.tmp-brickE3'
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
    print('Brick E3 patch' + (' (check only, nothing will be written)' if check_only else ''))

    for p, s in ((mp, main_src), (hp, html_src)):
        if MARK in s:
            fail(MARK + ' marker already in ' + p + '. Brick E3 is applied (or half applied). '
                 'To redo it, restore both .bak-brickE3 files first.')
    for p, s in ((mp, main_src), (hp, html_src)):
        if NEED not in s:
            fail(NEED + ' marker not found in ' + p + '. Apply Brick E1 first.')
    print('  ok  prerequisites: BRICK E1 in main.py and chat_test.html, no BRICK E3 yet')

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
    write(hp, new_html)
    if MARK not in read(mp) or MARK not in read(hp):
        fail('write verification failed. Restore the .bak-brickE3 files.')
    print('DONE. Brick E3 applied to main.py and chat_test.html.')
    print('Next: docker compose down; docker compose up -d --build; then purge the Cloudflare cache for /app.')
    print('Rollback: cp main.py' + BAK + ' main.py; cp chat_test.html' + BAK + ' chat_test.html')


main()