"""Sistema unificado de tracking de costes por job.

Cualquier modo de generación de vídeos (Creator Reward Presidentes /
Pronósticos / Quitar Copy / Subs Auto, o TikTok Shop) reporta sus
costes aquí. La granularidad es **por línea (call_kind)** — cada API
externa con coste pasa por uno de los helpers `record_*()`.

Funcionamiento:
  - Cada thread/job activa un `CostTracker` con `start_job(job_id, mode, ...)`.
  - Los helpers `record_openai_chat()`, `record_minimax_tts()` etc.
    suman al tracker activo en ese thread (vía contextvar).
  - Al finalizar el job, `finalize_and_persist()` guarda el snapshot en
    Redis y devuelve el total.

Persistencia Redis (mismo Upstash que TikTok Shop, prefijo `tiktok_shop:`):
  - `cost:job:{job_id}` → JSON con breakdown completo (TTL 1 año).
  - `cost:index:{program}:{YYYY-MM}` → lista append-only de job_ids del mes.
  - `cost:by_user:{username}` → SET de job_ids ligados al user.

Documentación obligatoria para AÑADIR un nuevo modo o API:
  1. Si la API es nueva (no `openai_chat`/`whisper`/`minimax_tts`), añade
     un helper `record_<api>` con su tarifa actualizada.
  2. En el runner del modo, llama `start_job(...)` al entrar y
     `finalize_and_persist()` al salir (try/finally).
  3. En CADA call a la API externa, llama al `record_*` correspondiente
     justo después del response (con tokens/chars/segundos reales).
  4. Si el modo no consume APIs externas (todo local), igualmente llama
     `start_job` + `finalize_and_persist` — quedará registrado con coste 0
     y tiempo de ejecución (útil para análisis).
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Tarifas — actualizar manualmente si cambian. Fuente: docs oficiales (2026).
# ---------------------------------------------------------------------------
# OpenAI gpt-4o-mini: $0.15 input + $0.60 output por 1M tokens
OPENAI_GPT4O_MINI_INPUT_PER_1M = 0.15
OPENAI_GPT4O_MINI_OUTPUT_PER_1M = 0.60
# OpenAI Whisper API: $0.006 por minuto de audio
OPENAI_WHISPER_PER_MIN = 0.006
# MiniMax speech-02-turbo: $0.06 por 1000 caracteres (≈ TikTok Shop config)
MINIMAX_TTS_PER_1K_CHARS = 0.06


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class CostLine:
    """Una entrada de coste atómica (una llamada a API)."""
    kind: str                 # "openai_chat" | "openai_whisper" | "minimax_tts" | "atlas_cloud" | ...
    units: float              # tokens / chars / segundos / minutos según kind
    unit_label: str           # "tokens" | "chars" | "seconds" | ...
    cost_usd: float           # coste calculado en USD
    detail: str | None = None # texto libre opcional ("input gpt-4o-mini", "voice ness")


@dataclass
class JobCost:
    job_id: str
    program: str              # "creator_reward" | "tiktok_shop"
    mode: str                 # "presidents" | "pronosticos" | "copyright" | "subs_auto" | "tiktok_shop"
    user: str | None = None   # username (para filtrar)
    product_id: str | None = None  # solo TikTok Shop
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    lines: list[CostLine] = field(default_factory=list)
    title: str | None = None

    @property
    def total_usd(self) -> float:
        return sum(line.cost_usd for line in self.lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_usd"] = round(self.total_usd, 6)
        return d


# ---------------------------------------------------------------------------
# Contextvar — un tracker por job/thread
# ---------------------------------------------------------------------------
_active_tracker: ContextVar[JobCost | None] = ContextVar(
    "cost_tracker_active", default=None,
)


def start_job(
    job_id: str,
    program: str,
    mode: str,
    *,
    user: str | None = None,
    product_id: str | None = None,
    title: str | None = None,
) -> JobCost:
    """Inicia tracking para el job actual. Asociado al contextvar — todos los
    `record_*` siguientes en este thread/coroutine añaden a este JobCost."""
    job = JobCost(
        job_id=job_id,
        program=program,
        mode=mode,
        user=user,
        product_id=product_id,
        title=title,
    )
    _active_tracker.set(job)
    return job


def get_active() -> JobCost | None:
    return _active_tracker.get()


def _add_line(line: CostLine) -> None:
    job = _active_tracker.get()
    if job is None:
        # Sin tracker activo (modo dev / test / call directa fuera de un job).
        # Nos callamos para no romper el flow — solo se pierde el dato.
        return
    job.lines.append(line)


# ---------------------------------------------------------------------------
# Recorders públicos — una función por tipo de API
# ---------------------------------------------------------------------------
def record_openai_chat(
    *,
    input_tokens: int,
    output_tokens: int,
    model: str = "gpt-4o-mini",
    detail: str | None = None,
) -> float:
    """Registra una call a la Chat Completions API de OpenAI. Devuelve coste."""
    # Solo conocemos gpt-4o-mini de momento; cualquier otro usa esa misma rate
    # como aproximación (mejor que perder el dato). Si añadís gpt-5 etc.,
    # añadid sus rates aquí.
    cost = (
        (input_tokens / 1_000_000) * OPENAI_GPT4O_MINI_INPUT_PER_1M
        + (output_tokens / 1_000_000) * OPENAI_GPT4O_MINI_OUTPUT_PER_1M
    )
    _add_line(CostLine(
        kind="openai_chat",
        units=input_tokens + output_tokens,
        unit_label="tokens",
        cost_usd=cost,
        detail=detail or f"{model} ({input_tokens}+{output_tokens})",
    ))
    return cost


def record_openai_whisper(*, audio_seconds: float, detail: str | None = None) -> float:
    """OpenAI Whisper API ($0.006/min)."""
    minutes = audio_seconds / 60.0
    cost = minutes * OPENAI_WHISPER_PER_MIN
    _add_line(CostLine(
        kind="openai_whisper",
        units=audio_seconds,
        unit_label="seconds",
        cost_usd=cost,
        detail=detail,
    ))
    return cost


def record_minimax_tts(*, chars: int, voice: str | None = None) -> float:
    """MiniMax speech synthesis ($0.06 / 1000 chars)."""
    cost = (chars / 1000.0) * MINIMAX_TTS_PER_1K_CHARS
    _add_line(CostLine(
        kind="minimax_tts",
        units=chars,
        unit_label="chars",
        cost_usd=cost,
        detail=f"voice={voice}" if voice else None,
    ))
    return cost


def record_atlas_cloud(
    *,
    seconds: float,
    tier: str,
    resolution: str | None = None,
    detail: str | None = None,
) -> float:
    """Atlas Cloud Seedance (TikTok Shop). Reutiliza la tarifa del módulo
    existente para mantener una única fuente de verdad."""
    try:
        from src.tiktok_shop.services.cost_calculator import estimate_video_cost
        cost = estimate_video_cost(tier, seconds, resolution or "720p")
    except Exception:
        cost = 0.0
    _add_line(CostLine(
        kind="atlas_cloud",
        units=seconds,
        unit_label="seconds",
        cost_usd=cost,
        detail=detail or f"tier={tier},res={resolution}",
    ))
    return cost


def record_custom(
    *, kind: str, units: float, unit_label: str, cost_usd: float, detail: str | None = None,
) -> float:
    """Escape hatch para APIs nuevas. Calcula el coste por fuera y registra
    aquí. Esto evita tener que tocar este archivo para experimentar."""
    _add_line(CostLine(
        kind=kind, units=units, unit_label=unit_label, cost_usd=cost_usd, detail=detail,
    ))
    return cost_usd


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def _redis():
    """Helper lazy — devuelve None si Upstash no está configurado."""
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis
        r = get_shop_redis()
        return r if r.is_available() else None
    except Exception:
        return None


def finalize_and_persist() -> JobCost | None:
    """Cierra el tracker activo, lo guarda en Redis y lo devuelve.

    NO falla si Redis no está disponible — sólo logea. Esto evita que un
    fallo de tracking rompa el job principal."""
    job = _active_tracker.get()
    if job is None:
        return None
    job.finished_at = time.time()
    _active_tracker.set(None)

    redis = _redis()
    if redis is None:
        return job

    try:
        month = datetime.fromtimestamp(job.started_at, tz=timezone.utc).strftime("%Y-%m")
        redis.set_json(f"cost:job:{job.job_id}", job.to_dict())
        redis.lpush(f"cost:index:{job.program}:{month}", job.job_id)
        # Índice cross-program también para filtros globales por mes.
        redis.lpush(f"cost:index:all:{month}", job.job_id)
        if job.user:
            redis.sadd(f"cost:by_user:{job.user}", job.job_id)
        if job.product_id:
            redis.sadd(f"cost:by_product:{job.product_id}", job.job_id)
    except Exception as e:
        print(f"[cost_tracking] persist error: {e}")
    return job


# ---------------------------------------------------------------------------
# Read API — usado por el endpoint /api/v1/stats/jobs
# ---------------------------------------------------------------------------
def _list_tiktok_shop_legacy(
    *,
    month: str | None,
    user: str | None,
    product_id: str | None,
    limit: int,
) -> list[dict]:
    """Lee `VideoGeneration` históricas de TikTok Shop y las convierte al
    formato unificado. Esto es para que el panel `/costs` muestre datos
    pre-existentes sin tener que migrar storage."""
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis
        from src.tiktok_shop.repos.generation_repo import GenerationRepo
        repo = GenerationRepo(get_shop_redis())
        gens = repo.list_recent(limit=limit * 2)
    except Exception as e:
        print(f"[cost_tracking] legacy load fail: {e}")
        return []

    out: list[dict] = []
    # Normaliza con/sin @ — históricamente algunos VideoGeneration guardan
    # `user_id=@pisadaviva` y otros `pisadaviva` según en qué versión del
    # código se crearon. Comparamos sin sensibilidad al @.
    def _norm(s: str | None) -> str:
        return (s or "").lstrip("@").strip().lower()

    user_norm = _norm(user) if user else None
    for g in gens:
        if g.deleted:
            continue
        if user_norm and _norm(g.user_id) != user_norm:
            continue
        if product_id and g.product_id != product_id:
            continue
        # Filtro de mes por created_at (ISO string).
        if month and g.created_at:
            try:
                if not g.created_at.startswith(month):
                    continue
            except Exception:
                pass
        cost = g.cost
        lines = []
        if cost.video_generation:
            lines.append({
                "kind": "atlas_cloud",
                "units": 0,
                "unit_label": "seconds",
                "cost_usd": float(cost.video_generation),
                "detail": f"tier={g.tier_used}",
            })
        if cost.voice_tts:
            lines.append({
                "kind": "minimax_tts",
                "units": 0,
                "unit_label": "chars",
                "cost_usd": float(cost.voice_tts),
                "detail": None,
            })
        if cost.other:
            lines.append({
                "kind": "other",
                "units": 0,
                "unit_label": "",
                "cost_usd": float(cost.other),
                "detail": None,
            })
        out.append({
            "job_id": g.id,
            "program": "tiktok_shop",
            "mode": "tiktok_shop",
            "user": g.user_id,
            "product_id": g.product_id,
            "title": f"{g.tier_used} · {g.user_id}/{g.product_id}",
            "started_at": _iso_to_ts(g.created_at),
            "finished_at": _iso_to_ts(g.completed_at),
            "lines": lines,
            "total_usd": float(cost.total or 0.0),
        })
    return out


def _iso_to_ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        from datetime import datetime
        # Normaliza el sufijo Z → +00:00 para fromisoformat
        s = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def list_jobs(
    *,
    month: str | None = None,
    program: str | None = None,
    mode: str | None = None,
    user: str | None = None,
    product_id: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Devuelve hasta `limit` JobCosts del mes filtrados. Si `month=None`
    usa el mes actual UTC.

    Combina dos fuentes:
      1. Jobs registrados por el nuevo `cost_tracking` (Creator Reward +
         futuros TikTok Shop tras el deploy).
      2. `VideoGeneration` históricas de TikTok Shop (read-only legacy)
         convertidas al mismo shape — para que el panel muestre datos
         que ya existían antes del nuevo sistema.
    """
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    out: list[dict] = []
    redis = _redis()

    # Fuente 1: nuevo sistema (Redis cost:job:*).
    if redis is not None:
        idx_key = f"cost:index:{program or 'all'}:{month}"
        ids: list[str] = redis.lrange(idx_key, 0, limit * 2)
        if user:
            user_set = set(redis.smembers(f"cost:by_user:{user}"))
            ids = [i for i in ids if i in user_set]
        if product_id:
            prod_set = set(redis.smembers(f"cost:by_product:{product_id}"))
            ids = [i for i in ids if i in prod_set]
        for job_id in ids[:limit]:
            raw = redis.get_json(f"cost:job:{job_id}")
            if not raw:
                continue
            if mode and raw.get("mode") != mode:
                continue
            out.append(raw)

    # Fuente 2: TikTok Shop legacy (VideoGeneration). Se omite si el filtro
    # de programa es explícitamente "creator_reward".
    if program != "creator_reward":
        legacy = _list_tiktok_shop_legacy(
            month=month, user=user, product_id=product_id, limit=limit,
        )
        # Evitar duplicados si el mismo job_id ya está en `out` (no debería,
        # pero por si en el futuro se persisten en ambos sitios).
        seen = {j["job_id"] for j in out}
        for j in legacy:
            if j["job_id"] in seen:
                continue
            if mode and mode != "tiktok_shop":
                continue
            out.append(j)

    # Ordenar por started_at desc + cap a limit.
    out.sort(key=lambda j: j.get("started_at") or 0, reverse=True)
    return out[:limit]


def aggregate_summary(jobs: list[dict]) -> dict[str, Any]:
    """Suma totales y agrupa por programa/mode/user para el panel de stats."""
    total = 0.0
    by_program: dict[str, float] = {}
    by_mode: dict[str, float] = {}
    by_user: dict[str, float] = {}
    by_kind: dict[str, float] = {}
    count = 0
    for j in jobs:
        amt = float(j.get("total_usd") or sum(l.get("cost_usd", 0) for l in j.get("lines", [])))
        total += amt
        count += 1
        by_program[j.get("program", "?")] = by_program.get(j.get("program", "?"), 0.0) + amt
        by_mode[j.get("mode", "?")] = by_mode.get(j.get("mode", "?"), 0.0) + amt
        u = j.get("user") or "(sin usuario)"
        by_user[u] = by_user.get(u, 0.0) + amt
        for line in j.get("lines", []):
            k = line.get("kind", "?")
            by_kind[k] = by_kind.get(k, 0.0) + line.get("cost_usd", 0.0)
    return {
        "total_usd": round(total, 4),
        "count": count,
        "by_program": {k: round(v, 4) for k, v in by_program.items()},
        "by_mode": {k: round(v, 4) for k, v in by_mode.items()},
        "by_user": {k: round(v, 4) for k, v in by_user.items()},
        "by_kind": {k: round(v, 4) for k, v in by_kind.items()},
    }
