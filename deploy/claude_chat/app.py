"""Claude Chat backend (Agent SDK, suscripcion Max). Chat con imagenes +
INYECCION de Remote Control a un chat concreto via tmux gestionado:
`claude --resume <id>` + `/remote-control` -> ese chat aparece en la app movil.
Atado a 172.18.0.1, gate X-API-Key. acceptEdits, sin Bash en el chat web."""
from __future__ import annotations
import json, os, glob, time, asyncio, subprocess, re, shlex
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

HOME = os.path.expanduser("~")
PROJECTS_DIR = Path(HOME) / ".claude" / "projects"
PROY = Path(HOME) / "proyectos"
UPLOADS = Path(HOME) / "claude_chat" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
TITLES = Path(HOME) / "claude_chat" / "titles.json"
# Lista de UUIDs que el auto-restore levanta al reiniciar el server.
# El usuario la gestiona desde la UI (pin/unpin). Persistente entre reboots.
ALWAYS_ON = Path(HOME) / ".claude" / "remote_state" / "always_on.json"
ALWAYS_ON.parent.mkdir(parents=True, exist_ok=True)
CLAUDE_BIN = str(Path(HOME) / ".local" / "bin" / "claude")
SAFE_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write", "MultiEdit",
              "WebSearch", "WebFetch", "TodoWrite", "NotebookEdit"]
DQ = chr(34)
SQ = chr(39)


def _api_key():
    env = Path(HOME) / "TikTok_Automation_Python" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("API_KEY="):
                return line.split("=", 1)[1].strip().strip(DQ + SQ)
    return os.getenv("API_KEY")


API_KEY = _api_key()
app = FastAPI(title="Claude Chat")


def _auth(x):
    if API_KEY and x != API_KEY:
        raise HTTPException(401, "unauthorized")


def _real_projects():
    try:
        return [p.name for p in PROY.iterdir() if (p / ".git").is_dir()]
    except Exception:
        return []


def _resolve_dir(name):
    if not name:
        return None
    if (PROY / name).is_dir():
        return name
    for d in _real_projects():
        if d.replace("_", "-") == name:
            return d
    return None


def _proj(encoded):
    suffix = encoded.split("-proyectos-", 1)[-1] if "-proyectos-" in encoded else encoded.lstrip("-")
    return _resolve_dir(suffix) or suffix


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _preview(fp):
    first = None
    last = None
    n = 0
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                msg = ev.get("message") or {}
                role = msg.get("role") or ev.get("type")
                t = _text(msg.get("content"))
                if role == "user" and t.strip() and not first:
                    first = t.strip()[:120]
                if t.strip():
                    last = t.strip()[:160]
                    n += 1
    except Exception:
        pass
    return {"title": first or "(sin titulo)", "last": last, "turns": n, "mtime": os.path.getmtime(fp)}


def _load_titles():
    try:
        return json.loads(TITLES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_title(sid, title):
    d = _load_titles()
    if title:
        d[sid] = title
    else:
        d.pop(sid, None)
    TITLES.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _rc_name(sid):
    return "rc_" + sid.replace("-", "")[:16]


def _rc_active():
    out = _tmux("ls").stdout or ""
    return [ln.split(":")[0] for ln in out.splitlines() if ln.startswith("rc_")]


def _always_on_load() -> set[str]:
    """Set de UUIDs marcados por el usuario como 'arranca al reiniciar'.
    Se guardan como JSON `{"uuids": ["...", "..."]}` para que el mismo
    archivo lo pueda leer `restore_chat_sessions.sh` con `jq` o python.
    """
    try:
        d = json.loads(ALWAYS_ON.read_text(encoding="utf-8"))
        return set(d.get("uuids", []))
    except Exception:
        return set()


def _always_on_save(uuids: set[str]) -> None:
    ALWAYS_ON.write_text(
        json.dumps({"uuids": sorted(uuids)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@app.get("/health")
def health():
    return {"ok": True, "auth": bool(API_KEY)}


@app.get("/sessions")
def sessions(x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    active = set(_rc_active())
    titles = _load_titles()
    always_on = _always_on_load()
    out = []
    for d in sorted(glob.glob(str(PROJECTS_DIR / "*proyectos*"))):
        proj = _proj(os.path.basename(d))
        for fp in glob.glob(os.path.join(d, "*.jsonl")):
            sid = os.path.basename(fp)[:-6]
            entry = {
                "id": sid,
                "project": proj,
                "remote": _rc_name(sid) in active,
                "always_on": sid in always_on,
                **_preview(fp),
            }
            if titles.get(sid):
                entry["title"] = titles[sid]
            out.append(entry)
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return {"projects": sorted(_real_projects()), "sessions": out}


@app.get("/remote/always-on")
def always_on_list(x_api_key: str | None = Header(None)):
    """Devuelve la lista de UUIDs marcados como 'arranca al reiniciar'.
    Usado por `restore_chat_sessions.sh` y por la UI para saber cuáles
    están marcados actualmente."""
    _auth(x_api_key)
    return {"uuids": sorted(_always_on_load())}


@app.post("/remote/always-on")
def always_on_toggle(session_id: str = Form(...), enabled: bool = Form(...),
                     x_api_key: str | None = Header(None)):
    """Toggle del pin de una sesión: `enabled=True` la añade a la lista
    de arranque; `enabled=False` la quita. Idempotente."""
    _auth(x_api_key)
    s = _always_on_load()
    before = len(s)
    if enabled:
        s.add(session_id)
    else:
        s.discard(session_id)
    _always_on_save(s)
    return {"ok": True, "always_on": session_id in s, "total": len(s), "changed": len(s) != before}


@app.post("/rename")
def rename(session_id: str = Form(...), title: str = Form(""),
           x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    _save_title(session_id, title.strip()[:80])
    return {"ok": True, "title": title.strip()[:80]}


@app.get("/projects")
def projects(x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    return {"projects": sorted(_real_projects())}


@app.get("/session/{sid}")
def session_detail(sid: str, x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    for d in glob.glob(str(PROJECTS_DIR / "*proyectos*")):
        fp = os.path.join(d, sid + ".jsonl")
        if os.path.exists(fp):
            msgs = []
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    msg = ev.get("message") or {}
                    role = msg.get("role")
                    if role not in ("user", "assistant"):
                        continue
                    t = _text(msg.get("content"))
                    if t.strip():
                        msgs.append({"role": role, "text": t.strip()})
            return {"id": sid, "project": _proj(os.path.basename(d)), "messages": msgs,
                    "remote": _rc_name(sid) in set(_rc_active())}
    raise HTTPException(404, "session not found")


@app.post("/remote/start")
async def remote_start(session_id: str = Form(...), project: str = Form(""),
                       x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    real = _resolve_dir(project)
    cwd = str(PROY / real) if real else str(PROY)
    name = _rc_name(session_id)
    _tmux("kill-session", "-t", name)
    # CLAVE de robustez: `claude --resume <id>` SIN prompt falla en muchas
    # sesiones ("No deferred tool marker... provide a prompt") y la sesion se
    # muere. Lanzando con un prompt minimo, arranca fiable y queda viva. El
    # prompt le pide solo confirmar y esperar -> ruido minimo en el chat.
    reconnect = "Reconectado desde la web. Responde solo 'ok' y espera mi siguiente mensaje; no edites ni ejecutes nada."
    _tmux("new-session", "-d", "-s", name, "-x", "200", "-y", "50", "-c", cwd,
          CLAUDE_BIN + " --resume " + session_id +
          " --permission-mode acceptEdits " + shlex.quote(reconnect))
    await asyncio.sleep(13)
    _tmux("send-keys", "-t", name, "/remote-control", "Enter")
    await asyncio.sleep(8)
    # Pido mostrar QR/URL (space) y capturo con scrollback por si scrolleo.
    _tmux("send-keys", "-t", name, "Space")
    await asyncio.sleep(2)
    pane = _tmux("capture-pane", "-t", name, "-p", "-S", "-60").stdout or ""
    m = re.search(r"https://claude\.ai/code/\S+", pane)
    url = m.group(0).rstrip(".") if m else None
    # Cerrar el menu "Continue" que aparece tras conectar -> entra al chat en
    # vivo. Si no, la app sale "en linea" pero no responde (queda en el menu).
    _tmux("send-keys", "-t", name, "Enter")
    await asyncio.sleep(1)
    return {"ok": True, "remote": name in _rc_active(), "url": url,
            "msg": "Abre este chat en la app de Claude (o el enlace)."}


@app.post("/remote/stop")
def remote_stop(session_id: str = Form(...), x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    _tmux("kill-session", "-t", _rc_name(session_id))
    return {"ok": True}


@app.get("/remote/active")
def remote_active(x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    return {"active": _rc_active()}


@app.post("/remote/start-all")
async def remote_start_all(x_api_key: str | None = Header(None)):
    """Activa Remote Control en TODOS los chats marcados como always-on.
    Si no hay ninguno marcado, escanea las últimas 10 sesiones y arranca
    las que tengan proyecto resoluble bajo ~/proyectos/. Idempotente:
    los que ya estén con remote activo se saltan.

    Devuelve por cada UUID: {uuid, project, started (bool), remote (bool),
    url, skipped_reason}.
    """
    _auth(x_api_key)
    active = set(_rc_active())
    targets: list[tuple[str, str]] = []

    # 1) Prioridad: la lista always-on marcada por el usuario.
    always_on = _always_on_load()
    if always_on:
        titles = _load_titles()
        # Para cada UUID buscar su proyecto real (leyendo el directorio
        # PROJECTS_DIR/*proyectos*).
        for sid in always_on:
            proj = ""
            for d in glob.glob(str(PROJECTS_DIR / "*proyectos*")):
                if os.path.exists(os.path.join(d, sid + ".jsonl")):
                    proj = _proj(os.path.basename(d))
                    break
            targets.append((sid, proj))
    else:
        # 2) Fallback: sin always-on aún → coger las 10 sesiones más
        # recientes con proyecto resoluble. Suele coincidir con lo que
        # el usuario quiere "activo por defecto" antes de configurar pins.
        candidates = []
        for d in sorted(glob.glob(str(PROJECTS_DIR / "*proyectos*"))):
            proj = _proj(os.path.basename(d))
            if not _resolve_dir(proj):
                continue
            for fp in glob.glob(os.path.join(d, "*.jsonl")):
                sid = os.path.basename(fp)[:-6]
                mtime = os.path.getmtime(fp)
                candidates.append((mtime, sid, proj))
        candidates.sort(reverse=True)
        targets = [(sid, proj) for _mtime, sid, proj in candidates[:10]]

    results: list[dict] = []

    async def _spawn_one(sid: str, proj: str):
        name = _rc_name(sid)
        if name in active:
            return {"uuid": sid, "project": proj, "started": False,
                    "remote": True, "skipped_reason": "already_active"}
        try:
            # Reutilizamos remote_start (sin llamarlo directo para evitar
            # `Depends`/`Form` — replicamos aquí compacto).
            real = _resolve_dir(proj)
            cwd = str(PROY / real) if real else str(PROY)
            _tmux("kill-session", "-t", name)
            reconnect = "Reconectado desde la web. Responde solo 'ok' y espera mi siguiente mensaje; no edites ni ejecutes nada."
            _tmux("new-session", "-d", "-s", name, "-x", "200", "-y", "50", "-c", cwd,
                  CLAUDE_BIN + " --resume " + sid +
                  " --permission-mode acceptEdits " + shlex.quote(reconnect))
            await asyncio.sleep(13)
            _tmux("send-keys", "-t", name, "/remote-control", "Enter")
            await asyncio.sleep(8)
            _tmux("send-keys", "-t", name, "Space")
            await asyncio.sleep(2)
            pane = _tmux("capture-pane", "-t", name, "-p", "-S", "-60").stdout or ""
            m = re.search(r"https://claude\.ai/code/\S+", pane)
            url = m.group(0).rstrip(".") if m else None
            _tmux("send-keys", "-t", name, "Enter")
            await asyncio.sleep(1)
            return {"uuid": sid, "project": proj, "started": True,
                    "remote": name in _rc_active(), "url": url}
        except Exception as e:
            return {"uuid": sid, "project": proj, "started": False,
                    "remote": False, "error": str(e)[:200]}

    # Paralelo: los sleeps del send-keys son concurrent-safe (cada uno a su
    # propia tmux session). 6-8 chats en ~30-40s en vez de ~3 min en serie.
    if targets:
        results = await asyncio.gather(*(_spawn_one(sid, proj) for sid, proj in targets))

    return {
        "ok": True,
        "total_processed": len(results),
        "started": sum(1 for r in results if r.get("started")),
        "already_active": sum(1 for r in results if r.get("skipped_reason") == "already_active"),
        "failed": sum(1 for r in results if not r.get("remote")),
        "results": results,
    }


async def _run(prompt, project, session_id) -> AsyncIterator[str]:
    from claude_agent_sdk import query, ClaudeAgentOptions
    real = _resolve_dir(project)
    cwd = str(PROY / real) if real else str(PROY)
    opts = ClaudeAgentOptions(cwd=cwd, permission_mode="acceptEdits",
                              allowed_tools=SAFE_TOOLS, resume=session_id or None)
    new_sid = None
    # El ~/.claude.json es compartido por ~10 servicios claude remote-control
    # + este backend; escrituras concurrentes lo corrompen puntualmente y el
    # spawn del SDK muere con "exit code 1". Se auto-repara en <1s, así que si
    # el fallo ocurre ANTES de emitir nada, reintentamos un par de veces.
    attempts = 0
    while True:
        attempts += 1
        produced = False
        try:
            async for m in query(prompt=prompt, options=opts):
                produced = True
                sid = getattr(m, "session_id", None)
                if not sid:
                    data = getattr(m, "data", None)
                    if isinstance(data, dict):
                        sid = data.get("session_id")
                if sid and not new_sid:
                    new_sid = sid
                    yield "event: session\ndata: " + json.dumps({"session_id": sid}) + "\n\n"
                for b in (getattr(m, "content", None) or []):
                    t = getattr(b, "text", None)
                    if t:
                        yield "event: text\ndata: " + json.dumps({"text": t}) + "\n\n"
            break
        except Exception as e:
            if not produced and attempts < 3:
                await asyncio.sleep(1.2)
                continue
            yield "event: error\ndata: " + json.dumps({"error": str(e)}) + "\n\n"
            break
    yield "event: done\ndata: {}\n\n"


@app.post("/chat")
async def chat(message: str = Form(""), project: str = Form(""),
               session_id: str = Form(""), images: list[UploadFile] = File(default=[]),
               x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    paths = []
    for up in images or []:
        safe = os.path.basename(up.filename or "img")
        dest = UPLOADS / (str(int(time.time())) + "_" + safe)
        dest.write_bytes(await up.read())
        paths.append(str(dest))
    prompt = message
    if paths:
        prompt += "\n\n[El usuario adjunta " + str(len(paths)) + " imagen(es). Usa Read para verlas:\n" + "\n".join(paths) + "\n]"
    return StreamingResponse(_run(prompt, project, session_id or None), media_type="text/event-stream")


# --- Estado de la credencial OAuth (suscripcion Max del host) --------------
# El chat usa las creds de ~/.claude/.credentials.json. Cuando el refresh
# token llega a su caducidad DURA, Claude Code vacia los tokens y todos los
# chats fallan con "OAuth session expired and could not be refreshed" aunque
# los servicios sigan vivos (por eso la UI los pintaba "en linea"). Este
# endpoint alimenta el aviso de la web para relogear ANTES de que caduque.
CREDS = Path(HOME) / ".claude" / ".credentials.json"
AUTH_WARN_DAYS = 7


@app.get("/auth-status")
def auth_status(x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    now_ms = time.time() * 1000
    try:
        oauth = json.loads(CREDS.read_text()).get("claudeAiOauth", {})
    except Exception as e:
        return {"state": "missing", "days_left": 0.0, "expires_at": 0,
                "subscription": None, "detail": str(e)}
    refresh_exp = int(oauth.get("refreshTokenExpiresAt") or 0)
    has_tokens = bool(oauth.get("accessToken")) and bool(oauth.get("refreshToken"))
    days_left = (refresh_exp - now_ms) / 86400000 if refresh_exp else 0.0
    if not has_tokens or not refresh_exp or refresh_exp <= now_ms:
        state = "expired"
    elif days_left <= AUTH_WARN_DAYS:
        state = "warning"
    else:
        state = "ok"
    return {"state": state, "days_left": round(days_left, 1),
            "expires_at": refresh_exp,
            "subscription": oauth.get("subscriptionType")}
