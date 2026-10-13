"""Local server integration support. No secrets included. Requires SESSION_SIGNING_KEY >=32 chars."""
import base64,hashlib,hmac,json,os,secrets,time
from pathlib import Path
from urllib.parse import urlparse
from fastapi import HTTPException
from fastapi.responses import JSONResponse


# === rate limiter (in-memory, single-worker) ===
import threading as _rl_threading
from collections import deque as _rl_deque, defaultdict as _rl_defaultdict

_RL_LOCK = _rl_threading.Lock()
_RL_BUCKETS = _rl_defaultdict(_rl_deque)
_RL_DAILY_BUCKETS = _rl_defaultdict(_rl_deque)
_RL_WINDOW = 60
_RL_DAY_WINDOW = 86400
_RL_MAX = int(os.environ.get("RATE_LIMIT_AI_PER_MIN", "20") or "20")
_RL_DAILY_MAX = int(os.environ.get("DAILY_AI_QUOTA", "500") or "500")
_RL_PATHS = (
    "/api/chat/stream",
    "/api/chat",
    "/api/ai/agentic",
    "/api/ai/generate",
    "/api/analyze-funnel",
    "/api/proactive-suggest",
    "/api/generate-tasks",
    "/api/generate-strategy",
    "/api/standup",
    "/api/tts",
)

def check_rate_limit(member_id, path):
    """Return (kind, cap) if exceeded, else None. Sliding windows per member."""
    if _RL_MAX <= 0 and _RL_DAILY_MAX <= 0:
        return None
    if not path.startswith(_RL_PATHS):
        return None
    now = time.time()
    with _RL_LOCK:
        if _RL_MAX > 0:
            q = _RL_BUCKETS[member_id]
            while q and now - q[0] > _RL_WINDOW:
                q.popleft()
            if len(q) >= _RL_MAX:
                return ("minute", _RL_MAX)
        if _RL_DAILY_MAX > 0:
            dq = _RL_DAILY_BUCKETS[member_id]
            while dq and now - dq[0] > _RL_DAY_WINDOW:
                dq.popleft()
            if len(dq) >= _RL_DAILY_MAX:
                return ("day", _RL_DAILY_MAX)
        if _RL_MAX > 0:
            _RL_BUCKETS[member_id].append(now)
        if _RL_DAILY_MAX > 0:
            _RL_DAILY_BUCKETS[member_id].append(now)
    return None
# === end rate limiter ===

COOKIE="e5_session"
TTL=7*24*3600
MAX_FILE=5*1024*1024
ALLOWED={".png",".jpg",".jpeg",".webp",".pdf",".txt",".csv"}

def key():
    value=os.environ.get("SESSION_SIGNING_KEY","")
    if len(value)<32:
        raise HTTPException(503,"Secure sessions are not configured: set SESSION_SIGNING_KEY.")
    return value.encode()

def pack(value):
    raw=base64.urlsafe_b64encode(json.dumps(value,separators=(",",":")).encode()).decode().rstrip("=")
    sig=hmac.new(key(),raw.encode(),hashlib.sha256).hexdigest()
    return raw+"."+sig

def unpack(value):
    try:
        raw,sig=value.split(".",1)
        if not hmac.compare_digest(sig,hmac.new(key(),raw.encode(),hashlib.sha256).hexdigest()):
            return None
        data=json.loads(base64.urlsafe_b64decode(raw+"="*((-len(raw))%4)))
        if data.get("exp",0)<time.time():return None
        return data
    except HTTPException:raise
    except Exception:return None

def set_session(response,member_id,admin=False):
    data={"uid":member_id,"sid":secrets.token_hex(24),"admin":bool(admin),"exp":int(time.time())+TTL}
    response.set_cookie(COOKIE,pack(data),httponly=True,secure=True,samesite="lax",max_age=TTL,path="/")
    return response

def csrf(session):
    return hmac.new(key(),("csrf:"+session["sid"]).encode(),hashlib.sha256).hexdigest()

def request_session(request):
    value=request.cookies.get(COOKIE)
    return unpack(value) if value else None

def require_member(request,supplied=None):
    identity=getattr(request.state,"member_id",None)
    if not identity:raise HTTPException(401,"Sign in with Whop.")
    if supplied and supplied not in ("default",identity):
        raise HTTPException(403,"Account identity does not match your session.")
    return identity

def llm_result(value):
    if not isinstance(value,str) or not value.strip():
        raise HTTPException(502,"AI returned an empty response.")
    if value.lstrip().lower().startswith("error:"):
        raise HTTPException(502,"AI provider is unavailable. Retry later.")
    return value

def check_upload(name,data):
    ext=Path(name or "").suffix.lower()
    if ext not in ALLOWED:raise HTTPException(415,"Unsupported proof type.")
    if not data:raise HTTPException(400,"Empty proof file.")
    if len(data)>MAX_FILE:raise HTTPException(413,"Proof exceeds 5 MB.")
    signatures={".png":b"\x89PNG\r\n\x1a\n",".jpg":b"\xff\xd8\xff",".jpeg":b"\xff\xd8\xff",".pdf":b"%PDF-"}
    if ext in signatures and not data.startswith(signatures[ext]):
        raise HTTPException(415,"File contents do not match its extension.")
    if ext==".webp" and not (data[:4]==b"RIFF" and data[8:12]==b"WEBP"):
        raise HTTPException(415,"Invalid WebP file.")
    if ext in (".txt",".csv"):
        try:data.decode("utf-8")
        except UnicodeError:raise HTTPException(415,"Use UTF-8 text files.")
        if b"\x00" in data:raise HTTPException(415,"Binary contents are not accepted as text.")
    return ext

async def security_gate(request,call_next):
    path=request.url.path
    # Readiness exposes no account/database details.
    public={"/","/auth/whop","/auth/whop/callback","/auth/admin","/admin_login","/favicon.ico","/api/health","/staging"}
    if path in public or path.startswith("/static/"):
        return await call_next(request)
    if path=="/api/webhook/whop":
        return JSONResponse({"error":"Webhook disabled until provider signature verification is implemented."},status_code=501)
    try:
        session=request_session(request)
        if not session:
            if path.startswith("/api/"):return JSONResponse({"detail":"Sign in with Whop."},status_code=401)
            return JSONResponse({"detail":"Sign in through /auth/whop."},status_code=401)
        request.state.member_id=session["uid"]
        request.state.session=session
        if path=="/api/check-inactive" and not session.get("admin"):
            return JSONResponse({"detail":"Admin session required."},status_code=403)
        if request.method not in ("GET","HEAD","OPTIONS"):
            token=request.headers.get("X-CSRF-Token","")
            if not hmac.compare_digest(token,csrf(session)):
                return JSONResponse({"detail":"Invalid or missing CSRF token."},status_code=403)
            origin=request.headers.get("Origin")
            expected=os.environ.get("APP_ORIGIN","").rstrip("/")
            if origin and origin.rstrip("/")!=(expected or str(request.base_url).rstrip("/")):
                return JSONResponse({"detail":"Origin is not permitted."},status_code=403)
        if not session.get("admin"):
            lim = check_rate_limit(request.state.member_id, path)
            if lim is not None:
                _kind, _cap = lim
                if _kind == "minute":
                    _msg = "Rate limit reached: " + str(_cap) + " AI requests per minute. Please wait a moment and retry."
                else:
                    _msg = "Daily limit reached: " + str(_cap) + " AI requests per day. Resets at midnight UTC."
                return JSONResponse({"detail": _msg}, status_code=429)
        return await call_next(request)
    except HTTPException as e:
        return JSONResponse({"detail":e.detail},status_code=e.status_code)

def checked_connection(namespace):
    conn=namespace["get_db_connection"]()
    if conn is None:raise HTTPException(503,"Database unavailable; no changes were saved.")
    return conn

def install_strict_database(namespace):
    """All write helpers fail closed. No production success-on-failure fallbacks."""
    def execute(sql,args):
        conn=checked_connection(namespace)
        try:
            with conn:
                with conn.cursor() as cur:cur.execute(sql,args)
        except Exception:
            raise HTTPException(503,"Database write failed; no success was confirmed.")
        finally:conn.close()
        return True
    def upsert(table,member,data):
        return execute(f"INSERT INTO {table} (member_id,data) VALUES (%s,%s) ON CONFLICT(member_id) DO UPDATE SET data=EXCLUDED.data",(member,json.dumps(data)))
    def add_proof(member,filename,filepath):
        return execute("INSERT INTO proof_files (member_id,data) VALUES (%s,%s)",(member,json.dumps({"filename":filename,"filepath":filepath})))
    def add_win(member,text,revenue):
        return execute("INSERT INTO wins (member_id,data) VALUES (%s,%s)",(member,json.dumps({"win_text":text,"revenue_amount":revenue})))
    def add_score(member,score):
        return execute("INSERT INTO scores (member_id,score) VALUES (%s,%s)",(member,score))
    def add_standup(member,task,actions,links,text,metrics,score,review,evidence,proof_files=None):
        data={"task_id":task,"tasks_completed":actions,"asset_links":links,"asset_text":text,"metrics":metrics,"score":score,"review":review,"evidence":evidence,"proof_files":proof_files or []}
        return execute("INSERT INTO standups (member_id,data) VALUES (%s,%s)",(member,json.dumps(data)))
    def save_funnel(member,data):
        return execute("INSERT INTO funnels(member_id,data) VALUES (%s,%s) ON CONFLICT(member_id) DO UPDATE SET data=EXCLUDED.data,updated_at=CURRENT_TIMESTAMP",(member,json.dumps(data)))
    namespace.update(db_upsert_profile=lambda m,d:upsert("profiles",m,d),db_upsert_journey=lambda m,d:upsert("journeys",m,d),
                     db_add_proof=add_proof,db_add_win=add_win,db_add_score=add_score,db_add_standup=add_standup,db_save_funnel=save_funnel)
    def rows(sql,args):
        conn=checked_connection(namespace)
        try:
            with conn.cursor() as cur:
                cur.execute(sql,args)
                return cur.fetchall()
        except Exception:
            raise HTTPException(503,"Database read failed; account data could not be verified.")
        finally:conn.close()
    def get_profile(member):
        result=rows("SELECT data FROM profiles WHERE member_id=%s",(member,))
        return result[0]["data"] if result else None
    def get_journey(member):
        result=rows("SELECT data FROM journeys WHERE member_id=%s",(member,))
        return result[0]["data"] if result else {"current_day":1,"current_phase":"Phase 1","current_task_id":"p1_t1","tasks_completed":[],"streak":0,"last_standup_date":None,"xp_total":0,"badges":[]}
    def data_list(table,member):
        return [r["data"] for r in rows(f"SELECT data FROM {table} WHERE member_id=%s ORDER BY created_at DESC",(member,))]
    def get_funnel(member):
        result=rows("SELECT data FROM funnels WHERE member_id=%s",(member,))
        return result[0]["data"] if result else {"stages":[]}
    namespace.update(db_get_profile=get_profile,db_get_journey=get_journey,
        db_get_proofs=lambda m:data_list("proof_files",m),db_get_wins=lambda m:data_list("wins",m),
        db_get_scores=lambda m:[r["score"] for r in rows("SELECT score FROM scores WHERE member_id=%s ORDER BY created_at",(m,))],
        db_get_funnel=get_funnel)

def persist_review(namespace,member_id,old_journey,journey,standup,score):
    conn=checked_connection(namespace)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM journeys WHERE member_id=%s FOR UPDATE",(member_id,))
                row=cur.fetchone()
                if not row or row["data"]!=old_journey:
                    raise HTTPException(409,"Journey changed while grading. Refresh before resubmitting.")
                cur.execute("INSERT INTO standups(member_id,data) VALUES (%s,%s)",(member_id,json.dumps(standup)))
                cur.execute("INSERT INTO scores(member_id,score) VALUES (%s,%s)",(member_id,score))
                cur.execute("UPDATE journeys SET data=%s WHERE member_id=%s",(json.dumps(journey),member_id))
    except HTTPException:raise
    except Exception:raise HTTPException(503,"Review could not be saved. No task completion was confirmed.")
    finally:conn.close()

def save_strategy(namespace,member_id,data):
    conn=checked_connection(namespace)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO strategy_docs(member_id,data) VALUES (%s,%s) ON CONFLICT(member_id) DO UPDATE SET data=EXCLUDED.data",(member_id,json.dumps(data)))
    except Exception:raise HTTPException(503,"Strategy could not be saved.")
    finally:conn.close()
