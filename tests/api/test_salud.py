"""`/api/health/completo`: sondas con tope y detección de la cola atascada."""

from __future__ import annotations

import time

from src.api.routers import salud
from src.queue.models import Job, JobMode, JobStatus


def _job(status, *, creado=0.0, empezado=None, programado=None) -> Job:
    j = Job(mode=JobMode.PRESIDENTS, title="t", status=status)
    j.created_at = creado
    j.started_at = empezado
    j.scheduled_for = programado
    return j


def test_corriendo_demasiado_es_atascado():
    ahora = 10_000.0
    jobs = [
        _job(JobStatus.RUNNING, empezado=ahora - salud.CORRIENDO_MAX_S - 60),
        _job(JobStatus.RUNNING, empezado=ahora - 60),
    ]
    r = salud.analizar_cola(jobs, ahora, workers_vivos=2)
    assert r["corriendo"] == 2
    assert [a["estado"] for a in r["atascados"]] == ["corriendo"]
    assert r["ok"] is False


def test_pendiente_sin_nadie_corriendo_es_atascado_pero_programado_no():
    ahora = 10_000.0
    viejo = ahora - salud.PENDIENTE_MAX_S - 60
    jobs = [
        _job(JobStatus.PENDING, creado=viejo),
        _job(JobStatus.PENDING, creado=viejo, programado=ahora + 3600),  # madrugada
        _job(JobStatus.PENDING, creado=ahora - 30),
    ]
    r = salud.analizar_cola(jobs, ahora)
    assert len(r["atascados"]) == 1 and r["atascados"][0]["estado"] == "pendiente"


def test_pendiente_esperando_a_uno_que_corre_no_es_atascado():
    ahora = 10_000.0
    jobs = [
        _job(JobStatus.RUNNING, empezado=ahora - 120),
        _job(JobStatus.PENDING, creado=ahora - salud.PENDIENTE_MAX_S * 3),
    ]
    assert salud.analizar_cola(jobs, ahora, workers_vivos=2)["ok"] is True


def test_sin_workers_vivos_no_esta_bien():
    assert salud.analizar_cola([], time.time(), workers_vivos=0)["ok"] is False


def test_sonda_colgada_no_cuelga_la_peticion(monkeypatch):
    monkeypatch.setattr(salud, "_TOPE_SONDA_S", 0.3)
    t0 = time.monotonic()
    r = salud._sondear({"bien": lambda: {"x": 1}, "colgada": lambda: time.sleep(5), "rota": lambda: 1 / 0})
    assert time.monotonic() - t0 < 1.5
    assert r["bien"]["ok"] is True and r["bien"]["x"] == 1
    assert r["colgada"]["ok"] is False and "no responde" in r["colgada"]["error"]
    assert r["rota"]["ok"] is False


def test_endpoint(app_client, fake_job_queue, monkeypatch):
    monkeypatch.setattr(salud, "_redis_fabrica", lambda: {"ok": True})
    monkeypatch.setattr(salud, "_redis_compartido", lambda: {"ok": False, "error": "sin configurar"})
    monkeypatch.setattr(salud, "_drive", lambda: {"ok": True, "entradas": 3})
    fake_job_queue._jobs.append(_job(JobStatus.RUNNING, empezado=time.time() - salud.CORRIENDO_MAX_S - 5))
    r = app_client.get("/api/health/completo")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert set(d["fallos"]) == {"redis_compartido", "cola"}
    assert d["cola"]["atascados"][0]["estado"] == "corriendo"
    assert d["drive"]["entradas"] == 3
