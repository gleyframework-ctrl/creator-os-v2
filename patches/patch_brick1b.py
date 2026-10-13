#!/usr/bin/env python3
"""
BRICK 1B - workspace sync (localStorage snapshots to server, version-checked).
Patches BOTH main.py and chat_test.html. Works with or without Brick 1A applied.

Usage:
  python3 patch_brick1b.py --sql      print the Supabase SQL (run it first), writes nothing
  python3 patch_brick1b.py --check    dry run: verify every anchor in both files, writes nothing
  python3 patch_brick1b.py            patch /root/e5-ai-coach/main.py and chat_test.html
  python3 patch_brick1b.py DIR        patch main.py and chat_test.html inside DIR

Copy-safety: this file contains NO less-than, greater-than or ampersand characters.
Anchors that need one use the placeholder {GT}, rebuilt with chr() at runtime.
Nothing is written unless every anchor in both files is found exactly once.
"""
import os
import shutil
import sys
from pathlib import Path

LT = chr(60)
GT = chr(62)
AMP = chr(38)
MARKER_PY = "BRICK 1B: WORKSPACE SYNC"
MARKER_JS = "BRICK 1B: workspace sync"

SQL = """-- Run in Supabase SQL editor BEFORE deploying.
CREATE TABLE IF NOT EXISTS local_state (
  member_id  TEXT NOT NULL,
  tool_key   TEXT NOT NULL,
  data       JSONB NOT NULL DEFAULT '{}'::jsonb,
  client_ts  BIGINT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (member_id, tool_key)
);
-- Only needed if you already created the table without client_ts:
ALTER TABLE local_state ADD COLUMN IF NOT EXISTS client_ts BIGINT;
CREATE INDEX IF NOT EXISTS idx_local_state_updated
  ON local_state (member_id, updated_at DESC);
ALTER TABLE local_state ENABLE ROW LEVEL SECURITY;
"""


def A(s):
    return s.replace("{GT}", GT)


BACKEND = r'''# ============================================================
# BRICK 1B: WORKSPACE SYNC (localStorage snapshots, version-checked)
# Silent by design: DB problems are logged (throttled), never raised.
# Comparisons use the operator module (copy-safe, no angle brackets).
# ============================================================
import operator as _sop
from starlette.concurrency import run_in_threadpool as _sync_threadpool

SYNC_TOOL_KEYS = ("funnel", "launch", "reality", "content", "community",
                  "leads", "actions", "library", "dna")
SYNC_MAX_TOOL_BYTES = 1024 * 1024        # 1 MB per tool
SYNC_MAX_BODY_BYTES = 2 * 1024 * 1024    # 2 MB per request
SYNC_RATE_PER_MIN = 60                   # requests per member per minute
_SYNC_WINDOWS = {}
_SYNC_LOCK = threading.Lock()
_SYNC_LAST_ERROR_LOG = [0.0]


def _sync_log_error(msg):
    """Log at most one sync error line per minute."""
    now = time.time()
    if _sop.ge(now - _SYNC_LAST_ERROR_LOG[0], 60):
        _SYNC_LAST_ERROR_LOG[0] = now
        log.error("Sync: " + str(msg))


def _sync_conn():
    """Quiet DB connection for the sync endpoints (no per-call INFO log)."""
    try:
        if not all([PGHOST, PGDATABASE, PGUSER, PGPASSWORD]):
            return None
        return psycopg2.connect(host=PGHOST, database=PGDATABASE, user=PGUSER,
                                password=PGPASSWORD, port=PGPORT, cursor_factory=RealDictCursor)
    except Exception as e:
        _sync_log_error(f"DB Error: {e}")
        return None


def _sync_close(conn):
    try:
        conn.close()
    except Exception:
        pass


def _sync_allow(member_id):
    """Fixed 60s window per member. True if this request may proceed."""
    now = time.time()
    with _SYNC_LOCK:
        if _sop.gt(len(_SYNC_WINDOWS), 10000):
            for k, v in list(_SYNC_WINDOWS.items()):
                if _sop.ge(now - v[0], 60):
                    _SYNC_WINDOWS.pop(k, None)
        win = _SYNC_WINDOWS.get(member_id)
        if not win or _sop.ge(now - win[0], 60):
            win = [now, 0]
            _SYNC_WINDOWS[member_id] = win
        if _sop.ge(win[1], SYNC_RATE_PER_MIN):
            return False
        win[1] += 1
        return True


def _sync_iso(value):
    return value.isoformat() if value else None


def _sync_prepare(tool_key, item):
    """Validate one tool snapshot. Returns a dict with data_json/base/client_ts, or {"error": reason}."""
    if tool_key not in SYNC_TOOL_KEYS:
        return {"error": "unknown_tool"}
    if not isinstance(item, dict):
        return {"error": "bad_item"}
    data = item.get("data")
    if not isinstance(data, (dict, list)):
        return {"error": "bad_data"}
    try:
        data_json = json.dumps(data, allow_nan=False, separators=(",", ":"))
    except Exception:
        return {"error": "bad_data"}
    if _sop.gt(len(data_json.encode("utf-8")), SYNC_MAX_TOOL_BYTES):
        return {"error": "too_large"}
    base = item.get("base_updated_at")
    if isinstance(base, str) and base.strip():
        try:
            datetime.fromisoformat(base.strip())
            base = base.strip()
        except Exception:
            base = None
    else:
        base = None
    try:
        client_ts = int(item.get("client_ts"))
        if _sop.lt(client_ts, 0):
            client_ts = None
    except Exception:
        client_ts = None
    return {"data_json": data_json, "base": base, "client_ts": client_ts}


def _sync_write(member_id, prepared):
    """Version-checked upserts in one transaction. Returns {tool_key: result} or None on DB failure.
    A write only lands if the server copy is still the version the browser last saw (base_updated_at),
    or if no server copy exists yet. Otherwise the result is a conflict carrying the server copy."""
    conn = _sync_conn()
    if not conn:
        return None
    results = {}
    try:
        cur = conn.cursor()
        for tool_key, p in prepared.items():
            row = None
            if p["base"]:
                cur.execute(
                    "UPDATE local_state SET data = %s::jsonb, client_ts = %s, updated_at = NOW() "
                    "WHERE member_id = %s AND tool_key = %s AND updated_at = %s::timestamptz "
                    "RETURNING updated_at",
                    (p["data_json"], p["client_ts"], member_id, tool_key, p["base"]))
                row = cur.fetchone()
            if not row:
                cur.execute(
                    "INSERT INTO local_state (member_id, tool_key, data, client_ts, updated_at) "
                    "VALUES (%s, %s, %s::jsonb, %s, NOW()) "
                    "ON CONFLICT (member_id, tool_key) DO NOTHING RETURNING updated_at",
                    (member_id, tool_key, p["data_json"], p["client_ts"]))
                row = cur.fetchone()
            if row:
                results[tool_key] = {"status": "saved", "updated_at": _sync_iso(row["updated_at"])}
                continue
            cur.execute(
                "SELECT data, updated_at, client_ts FROM local_state WHERE member_id = %s AND tool_key = %s",
                (member_id, tool_key))
            srv = cur.fetchone()
            results[tool_key] = {
                "status": "conflict",
                "data": srv["data"] if srv else None,
                "updated_at": _sync_iso(srv["updated_at"]) if srv else None,
                "client_ts": srv["client_ts"] if srv else None,
            }
        conn.commit()
        cur.close()
        return results
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _sync_log_error(f"write failed: {e}")
        return None
    finally:
        _sync_close(conn)


def _sync_read(member_id):
    """Returns (tools, meta) or None on DB failure."""
    conn = _sync_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tool_key, data, updated_at, client_ts FROM local_state WHERE member_id = %s",
            (member_id,))
        rows = cur.fetchall()
        cur.close()
        tools, meta = {}, {}
        for r in rows:
            if r["tool_key"] in SYNC_TOOL_KEYS:
                tools[r["tool_key"]] = r["data"]
                meta[r["tool_key"]] = {"updated_at": _sync_iso(r["updated_at"]), "client_ts": r["client_ts"]}
        return (tools, meta)
    except Exception as e:
        _sync_log_error(f"read failed: {e}")
        return None
    finally:
        _sync_close(conn)


def _sync_remove(member_id, tool_key):
    """Delete one snapshot (tool_key) or all of them (tool_key None). Returns count or None."""
    conn = _sync_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        if tool_key:
            cur.execute("DELETE FROM local_state WHERE member_id = %s AND tool_key = %s", (member_id, tool_key))
        else:
            cur.execute("DELETE FROM local_state WHERE member_id = %s", (member_id,))
        n = max(0, cur.rowcount)
        conn.commit()
        cur.close()
        return n
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _sync_log_error(f"delete failed: {e}")
        return None
    finally:
        _sync_close(conn)


@app.get("/api/sync")
def sync_get(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        result = _sync_read(member_id)
    except Exception as e:
        _sync_log_error(f"GET /api/sync: {e}")
        result = None
    if result is None:
        return JSONResponse({"ok": False, "reason": "db_unavailable"}, headers=NO_CACHE_HEADERS)
    return JSONResponse({"ok": True, "tools": result[0], "meta": result[1]}, headers=NO_CACHE_HEADERS)


@app.post("/api/sync")
async def sync_post(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        if not _sync_allow(member_id):
            return {"ok": False, "reason": "rate_limited"}
        raw = await request.body()
        if not raw:
            return {"ok": False, "reason": "rejected"}
        if _sop.gt(len(raw), SYNC_MAX_BODY_BYTES):
            return {"ok": False, "reason": "too_large"}
        try:
            body = json.loads(raw)
        except Exception:
            body = None
        if not isinstance(body, dict):
            return {"ok": False, "reason": "rejected"}
        single = isinstance(body.get("tool_key"), str)
        items = {body["tool_key"]: body} if single else body.get("tools")
        if not isinstance(items, dict) or not items:
            return {"ok": False, "reason": "rejected"}
        results, prepared = {}, {}
        for k, item in list(items.items())[:len(SYNC_TOOL_KEYS)]:
            p = _sync_prepare(str(k), item)
            if "error" in p:
                results[str(k)] = {"status": "rejected", "reason": p["error"]}
            else:
                prepared[str(k)] = p
        if prepared:
            written = await _sync_threadpool(_sync_write, member_id, prepared)
            if written is None:
                return {"ok": False, "reason": "db_unavailable", "results": results}
            results.update(written)
        out = {"ok": True, "results": results}
        if single:
            one = results.get(body["tool_key"], {})
            out["status"] = one.get("status")
            out["updated_at"] = one.get("updated_at")
        return out
    except Exception as e:
        _sync_log_error(f"POST /api/sync: {e}")
        return {"ok": False, "reason": "error"}


@app.delete("/api/sync")
def sync_delete(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        qp = request.query_params
        tool_key = (qp.get("tool_key") or "").strip()
        wipe_all = (qp.get("all") or "").strip() in ("1", "true")
        if tool_key and tool_key not in SYNC_TOOL_KEYS:
            return {"ok": False, "reason": "unknown_tool"}
        if not tool_key and not wipe_all:
            return {"ok": False, "reason": "rejected"}
        n = _sync_remove(member_id, tool_key or None)
        if n is None:
            return {"ok": False, "reason": "db_unavailable"}
        return {"ok": True, "deleted": n}
    except Exception as e:
        _sync_log_error(f"DELETE /api/sync: {e}")
        return {"ok": False, "reason": "error"}
# ===== end BRICK 1B backend =====


'''

JS_CORE = r'''// ===== BRICK 1B: workspace sync (version-checked snapshots; never throws, never blocks UI) =====
const SYNC_KEYS=['funnel','launch','reality','content','community','leads','actions','library','dna'];
const SYNC_LABELS={funnel:'Funnel',launch:'Launch plan',reality:'Reality check',content:'Content',community:'Community',leads:'Leads',actions:'Action Board',library:'Library',dna:'Business DNA'};
const SYNC_URL='/api/sync',SYNC_DEBOUNCE=2000,SYNC_RETRY=15000,SYNC_BOOT_WAIT=3000,SYNC_MAX_REQ=1800000;
let _syncDownloaded=false,_syncMember='',_syncBootPromise=null,_syncBusy=false,_syncAgain=false,_syncTimer=null,_syncOk=false,_syncStopped=false,_syncMeta=null,_syncLoading=false;
function syncGt(a,b){a=num(a);b=num(b);if(a===b)return false;return Math.max(a,b)===a;}
function syncFp(v){try{const s=JSON.stringify(v===undefined?null:v);let h=0;for(let i=0;i!==s.length;i++)h=(h*31+s.charCodeAt(i))|0;return s.length+':'+h;}catch(e){return 'x';}}
function syncNoIds(v){try{return JSON.stringify(v,function(k,x){return k==='id'?undefined:x;});}catch(e){return '';}}
function syncIsEmpty(k,v){try{return syncNoIds(v)===syncNoIds(defaults()[k]);}catch(e){return false;}}
function syncMetaKey(){return 'creator_os_v5_sync:'+_syncMember;}
function syncLoadMeta(){let m=null;try{m=JSON.parse(localStorage.getItem(syncMetaKey())||'null');}catch(e){m=null;}if(!isObj(m))m={v:1,tools:{}};if(!isObj(m.tools))m.tools={};_syncMeta=m;return m;}
function syncSaveMeta(){try{if(_syncMeta)localStorage.setItem(syncMetaKey(),JSON.stringify(_syncMeta));}catch(e){}}
function syncEntry(k){if(!_syncMeta)syncLoadMeta();let m=_syncMeta.tools[k];if(!isObj(m)){const f=syncFp(S[k]);m={fp:f,lfp:f,base:null,cts:0};_syncMeta.tools[k]=m;}return m;}
function syncDirty(k){const m=syncEntry(k);const f=syncFp(S[k]);if(f===m.fp)return false;if(f===m.rej)return false;return true;}
function syncPending(){try{if(!_syncMember)return false;return SYNC_KEYS.some(function(k){return syncDirty(k);});}catch(e){return false;}}
function syncActive(){if(!SESSION.member_id)return false;if(_syncMember!==SESSION.member_id)return false;if(_syncStopped)return false;return true;}
function syncLabel(){try{if(!syncActive())return 'Saved on this device';if(!_syncDownloaded)return 'Saved on this device';if(syncPending())return 'Saved on this device · syncing…';return _syncOk?'Synced to your account':'Saved on this device';}catch(e){return 'Saved on this device';}}
function syncShowLabel(){try{const el=$('#savedInd');if(el){el.textContent=syncLabel();el.classList.add('show');clearTimeout(el._t);el._t=setTimeout(function(){el.classList.remove('show');},1800);}renderSide();}catch(e){}}
function syncLater(ms){try{clearTimeout(_syncTimer);_syncTimer=setTimeout(function(){syncUpload();},ms);}catch(e){}}
// Called by persistNow() after localStorage succeeds: records which tools changed and when.
function syncSchedule(){
 try{
  if(!syncActive())return;if(storageBlocked)return;
  const now=Date.now();
  SYNC_KEYS.forEach(function(k){const m=syncEntry(k);const f=syncFp(S[k]);if(f!==m.lfp){m.lfp=f;m.cts=now;}});
  syncSaveMeta();
  if(_syncDownloaded)syncLater(SYNC_DEBOUNCE);
 }catch(e){}
}
function syncRecover(k,value){
 try{const key='creator_os_v5_recovery:'+_syncMember;let r=null;try{r=JSON.parse(localStorage.getItem(key)||'null');}catch(e){r=null;}if(!isObj(r))r={};r[k]={at:Date.now(),data:value};localStorage.setItem(key,JSON.stringify(r));}catch(e){}
}
function syncToast(keys){
 try{const n=keys.map(function(k){return SYNC_LABELS[k]||k;});if(!n.length)return;const last=n.pop();toast((n.length?n.join(', ')+' and '+last:last)+' updated from another device.');}catch(e){}
}
function syncRefreshView(){
 try{if(_syncLoading)return;const a=document.activeElement;const typing=a?['INPUT','TEXTAREA','SELECT'].includes(a.tagName):false;
  if(typing){renderSide();return;}if(DR){renderSide();return;}if($('#modal').classList.contains('on')){renderSide();return;}render();}catch(e){}
}
// Put winning server copies into S, then mark them as the synced baseline.
function syncApply(winners){
 const applied=[];
 Object.keys(winners).forEach(function(k){
  try{const w=winners[k];const next=JSON.parse(JSON.stringify(S));next[k]=w.data;S=cleanState(next);
   const m=syncEntry(k);const f=syncFp(S[k]);m.fp=f;m.lfp=f;m.base=w.updated_at||null;m.cts=num(w.client_ts);delete m.rej;applied.push(k);
  }catch(e){}
 });
 if(applied.length){syncSaveMeta();try{persistNow();}catch(e){}syncRefreshView();}
 return applied;
}
// Rules for tools WITHOUT unsynced local edits. Tools with unsynced edits are uploaded next;
// the server's version check (base_updated_at) decides whether they win.
function syncMerge(d,fresh){
 const tools=isObj(d.tools)?d.tools:{},meta=isObj(d.meta)?d.meta:{};const winners={},lost=[];
 SYNC_KEYS.forEach(function(k){
  const m=syncEntry(k);if(syncDirty(k))return;
  const sm=isObj(meta[k])?meta[k]:{};
  if(!Object.prototype.hasOwnProperty.call(tools,k)){
   if(m.base){winners[k]={data:defaults()[k],updated_at:null,client_ts:0};return;}
   if(!syncIsEmpty(k,S[k]))m.fp='';
   return;
  }
  const data=tools[k],upd=sm.updated_at||null;
  if(upd){if(m.base===upd)return;}
  if(syncFp(data)===syncFp(S[k])){m.base=upd;return;}
  winners[k]={data:data,updated_at:upd,client_ts:sm.client_ts};
  if(m.base)return;if(fresh)return;if(syncIsEmpty(k,S[k]))return;
  syncRecover(k,S[k]);lost.push(k);
 });
 syncSaveMeta();
 if(Object.keys(winners).length)syncApply(winners);
 if(lost.length)syncToast(lost);
 _syncOk=true;
}
async function syncPost(tools){
 const ctl=new AbortController(),t=setTimeout(function(){ctl.abort();},30000);
 try{
  const r=await fetch(SYNC_URL,{method:'POST',credentials:'same-origin',headers:jsonHeaders(),body:JSON.stringify({tools:tools}),signal:ctl.signal});
  if(r.status===401){_syncStopped=true;return null;}
  if(!r.ok)return null;const d=await r.json();
  if(!isObj(d))return null;if(d.ok!==true)return null;return d;
 }catch(e){return null;}finally{clearTimeout(t);}
}
async function syncHandle(d,items,sentFp,final){
 const results=isObj(d.results)?d.results:{};const winners={},lost=[],retry={};
 Object.keys(results).forEach(function(k){
  if(!SYNC_KEYS.includes(k))return;const r=results[k];if(!isObj(r))return;const m=syncEntry(k);
  if(r.status==='saved'){m.base=r.updated_at||m.base;m.fp=sentFp[k];delete m.rej;return;}
  if(r.status==='rejected'){m.rej=sentFp[k];if(r.reason==='too_large')toast((SYNC_LABELS[k]||k)+' is too large to sync (1 MB limit). It stays saved on this device.');return;}
  if(r.status!=='conflict')return;if(r.data==null)return;
  if(syncFp(r.data)===sentFp[k]){m.base=r.updated_at;m.fp=sentFp[k];return;}
  if(!final){if(syncGt(items[k].client_ts,num(r.client_ts))){retry[k]={data:items[k].data,base_updated_at:r.updated_at,client_ts:items[k].client_ts};return;}}
  syncRecover(k,S[k]);winners[k]={data:r.data,updated_at:r.updated_at,client_ts:r.client_ts};lost.push(k);
 });
 syncSaveMeta();
 if(Object.keys(retry).length){const d2=await syncPost(retry);if(d2)await syncHandle(d2,retry,sentFp,true);}
 if(lost.length){syncApply(winners);syncToast(lost);}
}
function syncGroups(items){
 const out=[];let cur={},size=0;
 Object.keys(items).forEach(function(k){const n=JSON.stringify(items[k]).length;if(Object.keys(cur).length){if(syncGt(size+n,SYNC_MAX_REQ)){out.push(cur);cur={};size=0;}}cur[k]=items[k];size+=n;});
 if(Object.keys(cur).length)out.push(cur);return out;
}
async function syncUpload(){
 if(_syncBusy){_syncAgain=true;return;}
 let failed=false,sent=false;
 try{
  if(!_syncDownloaded)return;if(!syncActive())return;if(storageBlocked)return;
  if(navigator.onLine===false){syncLater(SYNC_RETRY);return;}
  const keys=SYNC_KEYS.filter(function(k){return syncDirty(k);});if(!keys.length)return;
  _syncBusy=true;const items={},sentFp={};
  keys.forEach(function(k){const m=syncEntry(k);sentFp[k]=syncFp(S[k]);items[k]={data:JSON.parse(JSON.stringify(S[k])),base_updated_at:m.base||null,client_ts:num(m.cts)||Date.now()};});
  for(const g of syncGroups(items)){const d=await syncPost(g);if(!d){failed=true;break;}sent=true;await syncHandle(d,g,sentFp,false);}
 }catch(e){failed=true;}
 finally{
  _syncBusy=false;
  if(failed){_syncOk=false;if(!_syncStopped)syncLater(SYNC_RETRY);}
  else if(sent){_syncOk=true;syncShowLabel();}
  if(_syncAgain){_syncAgain=false;syncLater(SYNC_DEBOUNCE);}
  else if(sent){if(syncPending())syncLater(SYNC_DEBOUNCE);}
 }
}
async function syncDownload(fresh){
 const member=_syncMember;let d=null;const ctl=new AbortController(),t=setTimeout(function(){ctl.abort();},15000);
 try{const r=await fetch(SYNC_URL,{credentials:'same-origin',headers:{'Accept':'application/json'},cache:'no-store',signal:ctl.signal});if(r.ok)d=await r.json();else if(r.status===401)_syncStopped=true;}
 catch(e){d=null;}finally{clearTimeout(t);}
 if(member!==_syncMember)return;
 try{if(isObj(d)){if(d.ok===true)syncMerge(d,fresh);}}catch(e){}
 _syncDownloaded=true;
 try{await syncUpload();}catch(e){}
 try{renderSide();}catch(e){}
}
// Start sync for the signed-in member: download first, never upload before that finishes.
function syncStart(fresh){
 try{
  if(!SESSION.member_id)return Promise.resolve();if(storageBlocked)return Promise.resolve();
  if(_syncMember===SESSION.member_id){if(_syncBootPromise)return _syncBootPromise;}
  if(fresh===undefined)fresh=!readStore(KEY);
  _syncMember=SESSION.member_id;_syncDownloaded=false;_syncOk=false;_syncStopped=false;_syncMeta=null;clearTimeout(_syncTimer);
  syncLoadMeta();SYNC_KEYS.forEach(function(k){syncEntry(k);});syncSaveMeta();
  _syncBootPromise=syncDownload(fresh);return _syncBootPromise;
 }catch(e){_syncDownloaded=true;return Promise.resolve();}
}
// Boot: a brand-new device waits up to 3 seconds for the server copy instead of flashing empty defaults.
async function syncBoot(){
 try{
  if(!SESSION.member_id)return;if(storageBlocked)return;
  const fresh=!readStore(KEY);const p=syncStart(fresh);if(!fresh)return;
  _syncLoading=true;const main=$('#main');
  if(main){const c=document.createElement('div');c.className='card';c.setAttribute('role','status');c.textContent='Loading your workspace…';main.replaceChildren(c);}
  await Promise.race([p,new Promise(function(res){setTimeout(res,SYNC_BOOT_WAIT);})]);
 }catch(e){}finally{_syncLoading=false;}
}
function syncResetLocal(){
 try{if(!_syncMember)return;clearTimeout(_syncTimer);if(!_syncMeta)syncLoadMeta();SYNC_KEYS.forEach(function(k){const f=syncFp(S[k]);_syncMeta.tools[k]={fp:f,lfp:f,base:null,cts:0};});syncSaveMeta();}catch(e){}
}
async function syncDeleteAll(){
 try{if(!SESSION.member_id)return false;const r=await fetch(SYNC_URL+'?all=1',{method:'DELETE',credentials:'same-origin',headers:jsonHeaders()});if(!r.ok)return false;const d=await r.json();return isObj(d)?d.ok===true:false;}catch(e){return false;}
}
// ===== end BRICK 1B core =====
'''

PY_PATCHES = [
    ("main.py: sync endpoints",
     "# ============================================================\n# MAIN (This MUST be at the very bottom)",
     "before", BACKEND),
]

HTML_PATCHES = [
    ("core: sync engine",
     "async function apiJSON(url,options={}){", "before", JS_CORE),
    ("persistNow: record changes + honest label",
     "localStorage.setItem(KEY,JSON.stringify(S));storageWarning=false;const el=$('#savedInd');if(el){el.textContent='Saved on this device';",
     "replace",
     "localStorage.setItem(KEY,JSON.stringify(S));storageWarning=false;syncSchedule();const el=$('#savedInd');if(el){el.textContent=syncLabel();"),
    ("top bar label",
     A('class="saved"{GT}Saved on this device'), "replace",
     A('class="saved"{GT}' + "'+syncLabel()+'")),
    ("sidebar label",
     ":REMOTE.error?'Local workspace':'Saved on this device')", "replace",
     ":REMOTE.error?'Local workspace':syncLabel())"),
    ("init: download before first render (fresh device waits up to 3s)",
     "route(true);refreshAccount();", "replace",
     "await syncBoot();route(true);refreshAccount();"),
    ("late sign-in: start sync",
     "if(KEY!=='creator_os_v5:anonymous'){S=loadWorkspace();}", "replace",
     "if(KEY!=='creator_os_v5:anonymous'){S=loadWorkspace();syncStart();}"),
    ("reset: also delete server copy",
     A("ACT.reset=()={GT}askConfirm('Reset device workspace?','Export a backup first. This clears this workspace only; server data and old Growth OS keys stay untouched.',()={GT}{S=mainDefaults(defaults());storageBlocked=false;persistNow();render();toast('Device workspace reset.');});"),
     "replace", "ACT.reset=function(){askConfirm('Reset workspace?','Export a backup first. This clears this workspace on this device and the synced copy in your account. Your journey, standups, wins and old Growth OS keys stay untouched.',function(){S=mainDefaults(defaults());storageBlocked=false;syncResetLocal();persistNow();render();toast('Workspace reset on this device. Removing the server copy…');syncDeleteAll().then(function(ok){toast(ok?'Workspace reset on this device and in your account.':'This device was reset, but the server copy could not be deleted. Run Reset again when you are online.');});});};"),
    ("copy: settings backup note",
     "Keep them secure. Device data does not sync across browsers.", "replace",
     "Keep them secure. Funnel, launch, reality check, content, community, leads, tasks, library and Business DNA sync to your account. Chat history, language and layout stay on this device."),
    ("copy: danger zone",
     "Reset affects only this workspace\u2019s device data. It does not delete server records or the original Growth OS data.", "replace",
     "Reset clears this workspace and the server copy of your synced tools. It does not delete your journey, standups, wins or the original Growth OS data."),
    ("copy: welcome card",
     "Everything saves automatically in this browser.", "replace",
     "Everything saves automatically and syncs to your account when you are signed in."),
    ("copy: restore backup",
     "This replaces the current device workspace. Export it first if you need to keep it. Server data and original keys are untouched.", "replace",
     "This replaces your current workspace on this device and, once synced, in your account. Export it first if you need to keep it. Original Growth OS keys are untouched."),
    ("copy: sign out",
     "Your saved workspace stays on this device. On a shared computer, export and reset it first.", "replace",
     "Your saved workspace stays on this device. Reset also deletes your synced copy, so on a shared computer export a backup before resetting."),
]

HTML_POST = ["syncSchedule();const el", "class=\"saved\"", "await syncBoot();route(true)", "S=loadWorkspace();syncStart();",
             "syncDeleteAll().then", "Synced to your account"]


def fail(msg):
    print("ABORTED - nothing was written.")
    print("Reason: " + msg)
    sys.exit(1)


def check(label, src, patches, marker):
    if marker in src:
        fail(label + " already contains the Brick 1B marker - already patched.")
    escaped = (AMP + "gt;", AMP + "lt;", AMP + "amp;")
    bad = []
    for name, anchor, mode, text in patches:
        for e in escaped:
            if e in anchor:
                fail("anchor '" + name + "' contains HTML-escaped text (copy damage?)")
        n = src.count(anchor)
        print("  [" + ("OK" if n == 1 else "FOUND " + str(n) + "x") + "] " + name)
        if n != 1:
            bad.append(name)
    if bad:
        fail(label + ": anchors missing or not unique: " + ", ".join(bad))


def apply(src, patches):
    for name, anchor, mode, text in patches:
        if mode == "before":
            new = text + anchor
        elif mode == "after":
            new = anchor + text
        else:
            new = text
        src = src.replace(anchor, new, 1)
    return src


def write(target, out, suffix):
    backup = target.with_name(target.name + ".bak-brick1b")
    shutil.copy2(target, backup)
    tmp = target.with_name(target.name + ".tmp-" + suffix)
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, target)
    print("PATCHED: " + str(target) + "   backup: " + str(backup))


def main():
    if "--sql" in sys.argv:
        print(SQL)
        return
    check_only = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = Path(args[0]) if args else Path("/root/e5-ai-coach")
    py_path, html_path = base / "main.py", base / "chat_test.html"
    for p in (py_path, html_path):
        if not p.is_file():
            fail("file not found: " + str(p))
    for c in (LT, GT, AMP):
        if c in JS_CORE or c in BACKEND:
            fail("inserted code contains a forbidden character (copy damage?)")
    py_src = py_path.read_text(encoding="utf-8")
    html_src = html_path.read_text(encoding="utf-8")
    print("main.py")
    check("main.py", py_src, PY_PATCHES, MARKER_PY)
    print("chat_test.html")
    check("chat_test.html", html_src, HTML_PATCHES, MARKER_JS)
    if check_only:
        print("CHECK PASSED - all anchors found exactly once in both files. Nothing written.")
        return
    py_out = apply(py_src, PY_PATCHES)
    html_out = apply(html_src, HTML_PATCHES)
    try:
        compile(py_out, str(py_path), "exec")
    except SyntaxError as e:
        fail("patched main.py does not compile: " + str(e))
    if py_out.count(MARKER_PY) != 1 or html_out.count(MARKER_JS) != 1:
        fail("post-check: marker count is wrong")
    for needle in HTML_POST:
        if needle not in html_out:
            fail("post-check: missing " + needle)
    for old_label in ("el.textContent='Saved on this device'", "class=\"saved\"" + GT + "Saved on this device",
                      "'Local workspace':'Saved on this device')", "does not sync across browsers",
                      "It does not delete server records"):
        if old_label in html_out:
            fail("post-check: an old device-only label survived: " + old_label.replace(GT, "{GT}"))
    write(py_path, py_out, "brick1b")
    write(html_path, html_out, "brick1b")
    print("Rollback: copy both .bak-brick1b files back, then rebuild the container.")


main()
