"""Entrega en el día programado (web de clientes).

Un vídeo programado para un día FUTURO se edita cuanto antes, pero el cliente
no lo ve, no lo descarga y no recibe el aviso hasta que empieza ese día (hora
de España). En la cola, lo que se entrega hoy pasa delante de lo programado.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

HOY = "2026-11-11"
FUTURO = "2026-11-14"


class FakeR:
    def __init__(self):
        self.kv = {}
        self.sets = {}

    def get_str(self, k):
        x = self.kv.get(k)
        return x if isinstance(x, str) else None

    def set_str(self, k, val):
        self.kv[k] = val
        return True

    def get_json(self, k):
        x = self.kv.get(k)
        return json.loads(x) if isinstance(x, str) and x[:1] in "{[" else None

    def set_json(self, k, val):
        self.kv[k] = json.dumps(val)
        return True

    def smembers(self, k):
        return set(self.sets.get(k, set()))

    def sadd(self, k, v):
        self.sets.setdefault(k, set()).add(v)
        return True

    def srem(self, k, v):
        self.sets.get(k, set()).discard(v)
        return True


class FakeWeb:
    def __init__(self, cuentas):
        self.cuentas = cuentas
        self.trial = {}

    def get(self, email):
        return self.cuentas.get(email)

    def set_trial_videos(self, email, n):
        self.trial[email] = n


@pytest.fixture
def box(monkeypatch):
    """Motor con Redis, cuenta web, cola y email de mentira. `box.hoy` mueve el
    calendario; `box.enviados` guarda los avisos de «vídeos listos»."""
    from src.api.routers.editor_auto import web_upload as wu
    from src.editor_auto import config as cfg
    from src.editor_auto.models import EditorUser
    from src.editor_auto.services import email_notify
    from src.queue import manager as mgr
    from src.queue.models import Job, JobStatus
    import src.editor_auto.repos.web_account_repo as war
    import src.editor_auto.services.retention_sweeper as rs

    estado = SimpleNamespace(hoy=HOY, hora=10, enviados=[], jobs=[])
    r = FakeR()
    user = EditorUser(name="ana", account_email="ana@x.com")
    web = FakeWeb({"ana@x.com": {"email": "ana@x.com", "planId": "pro", "username": "ana"}})

    monkeypatch.delenv("EDITOR_WHATSAPP_AVISOS", raising=False)
    monkeypatch.setattr(wu, "_hoy_madrid", lambda: estado.hoy)
    monkeypatch.setattr(wu, "_hora_madrid", lambda: estado.hora)
    monkeypatch.setattr(mgr, "_hoy_madrid", lambda: estado.hoy)
    monkeypatch.setattr(wu, "get_editor_redis", lambda: r)
    monkeypatch.setattr(wu, "_resolve_user", lambda claims: user)
    monkeypatch.setattr(wu, "_user_has_plan", lambda u: True)
    monkeypatch.setattr(wu, "_job_score", lambda j: 95)
    monkeypatch.setattr(wu, "_job_deliverable", lambda j, s: True)
    monkeypatch.setattr(wu, "UserRepo", lambda: SimpleNamespace(get=lambda uid: user, save=lambda u: None))
    monkeypatch.setattr(war, "get_web_account_repo", lambda: web)
    monkeypatch.setattr(cfg, "manual_approval_enabled", lambda: True)
    monkeypatch.setattr(cfg, "day_expires_at", lambda u, d: "")
    monkeypatch.setattr(rs, "expired_days", lambda uid: set())
    monkeypatch.setattr(email_notify, "is_configured", lambda: True)

    def _send(**kw):
        estado.enviados.append(kw)
        return {"ok": True}

    monkeypatch.setattr(email_notify, "send_videos_ready", _send)

    def poner_dia(day, *, status="completed", aprobado=True):
        """Un vídeo de `day` ya mandado a edición, con el job en `status`."""
        j = Job(mode="editor_auto", title="j1", params={"output_subdir": day})
        j.id = f"job-{day}"
        j.status = JobStatus(status)
        j.result_path = f"/salida/{day}/a_editado.mp4" if status == "completed" else None
        estado.jobs.append(j)
        r.set_json(f"webday_jobs:{user.id}:{day}", [{"filename": "a.mp4", "job_id": j.id}])
        r.sadd(f"webdays_sent:{user.id}", day)
        r.sadd("web_sent_index", f"{user.id}:{day}")
        if aprobado:
            r.sadd(f"webday_approved:{user.id}:{day}", "a_editado.mp4")
        return j

    estado.wu = wu
    estado.mgr = mgr
    estado.r = r
    estado.user = user
    estado.web = web
    estado.poner_dia = poner_dia
    estado.queue = SimpleNamespace(get_all=lambda: estado.jobs, posiciones_pendientes=lambda: {})
    estado.claims = SimpleNamespace(email="ana@x.com", day="", scope="upload", raw={})
    return estado


# ───────────── 1. Se edita cuanto antes ─────────────

def test_dia_futuro_no_espera_a_su_dia_para_editarse(box):
    assert box.wu._day_released(HOY) is True
    assert box.wu._day_released("2026-11-10") is True
    assert box.wu._day_released(FUTURO) is False
    # Antes devolvía las 00:00 UTC del día programado: no se tocaba hasta entonces.
    assert box.wu._edit_start_epoch(FUTURO, 0) is None
    assert box.wu._edit_start_epoch(FUTURO, 9) is None


def _mandar(box, monkeypatch, day):
    wu = box.wu
    import src.editor_auto.services.style_mapper as sm

    llamadas = []

    def _enqueue(queue, user, mount_path, d, **kw):
        llamadas.append({"day": d, **kw})
        return f"job-{len(llamadas)}"

    monkeypatch.setattr(wu, "_require_drive", lambda: None)
    monkeypatch.setattr(wu, "_is_admin", lambda u: False)
    monkeypatch.setattr(wu, "_user_plan", lambda u: None)
    monkeypatch.setattr(wu, "day_send_open", lambda d: True)
    monkeypatch.setattr(wu, "web_priority", lambda u, a=None: 50)
    monkeypatch.setattr(sm, "build_tool_flow", lambda cfg: [])
    monkeypatch.setattr(sm, "conservar_pasos_del_equipo", lambda nuevo, viejo: nuevo)
    monkeypatch.setattr(wu.drive_uploads, "list_day_files", lambda name, d: [{"filename": "a.mp4"}])
    monkeypatch.setattr(wu, "user_input_day_folder", lambda name, d: f"/entrada/{d}")
    monkeypatch.setattr(wu, "_enqueue_video", _enqueue)
    monkeypatch.setattr(wu, "_apuntar_envio", lambda *a, **k: None)
    res = wu.web_send_to_edit(box.claims, wu.SendToEditRequest(day=day), box.queue)
    return res, llamadas


def test_mandar_un_dia_futuro_encola_sin_retraso(box, monkeypatch):
    res, llamadas = _mandar(box, monkeypatch, FUTURO)
    assert [e["filename"] for e in res["enqueued"]] == ["a.mp4"]
    assert len(llamadas) == 1
    assert llamadas[0]["scheduled_for"] is None      # se edita cuanto antes
    assert llamadas[0]["count_quota"] is False       # no gasta la cuota de hoy
    assert llamadas[0]["priority"] == 50             # conserva la prioridad de su plan


def test_mandar_para_hoy_sigue_igual(box, monkeypatch):
    monkeypatch.setattr(box.wu, "_day_processing_start", lambda d, h: 0.0)  # ventana ya abierta
    _res, llamadas = _mandar(box, monkeypatch, HOY)
    assert llamadas[0]["scheduled_for"] is None
    assert llamadas[0]["count_quota"] is True


# ───────────── 2. En la cola, lo de hoy primero ─────────────

def test_cola_lo_de_hoy_pasa_antes_que_lo_programado(box):
    from src.queue.models import Job

    def job(jid, day, prio):
        j = Job(mode="editor_auto", title=jid, params={"output_subdir": day, "queue_priority": prio})
        j.id = jid
        return j

    programado_escala = job("programado", FUTURO, 90)
    hoy_basico = job("hoy-basico", HOY, 10)
    hoy_pro = job("hoy-pro", HOY, 50)
    cola = [programado_escala, hoy_basico, hoy_pro]
    orden = []
    while cola:
        sig = max(cola, key=box.mgr._client_order)
        orden.append(sig.id)
        cola.remove(sig)
    assert orden == ["hoy-pro", "hoy-basico", "programado"]
    # Llegado su día, compite por su plan como cualquier otro.
    box.hoy = FUTURO
    assert box.mgr._client_due(programado_escala) == 1
    assert max([hoy_basico, programado_escala], key=box.mgr._client_order).id == "programado"


def test_cola_subcarpeta_que_no_es_fecha_no_cambia(box):
    from src.queue.models import Job

    j = Job(mode="editor_auto", title="x", params={"output_subdir": "varios"})
    assert box.mgr._client_due(j) == 1


# ───────────── 3. El cliente lo ve el día que programó ─────────────

def test_editado_y_aprobado_antes_de_su_dia_no_se_entrega(box):
    wu = box.wu
    box.poner_dia(FUTURO)  # ya editado y aprobado por el revisor, tres días antes

    out = wu.web_output(box.claims, FUTURO, box.queue)
    assert out["ready"] == 0 and out["review"] == 0 and out["all_done"] is False
    v = out["videos"][0]
    assert v["scheduled"] is True and v["ready"] is False
    assert v["filename"] is None and v["in_review"] is False and v["running"] is False

    resumen = wu.web_days_summary(box.claims, box.queue)["days"][FUTURO]
    assert resumen == {**resumen, "total": 1, "ready": 0, "review": 0, "in_progress": 1, "all_done": False}

    box.wu.verify_ticket = lambda t: box.claims
    with pytest.raises(wu.APIError) as e:
        wu.web_download(FUTURO, "a_editado.mp4", "ticket")
    assert e.value.status_code == 409

    # Ni al aprobar, ni al abrir el panel, ni con el barrido sale el aviso.
    wu._maybe_notify_ready(box.user, FUTURO, box.queue)
    assert wu.notify_released_days(box.queue) == 0
    assert box.enviados == []


def test_llegado_su_dia_se_entrega_y_avisa_una_sola_vez(box):
    wu = box.wu
    box.poner_dia(FUTURO)
    wu.web_output(box.claims, FUTURO, box.queue)
    assert box.enviados == []

    box.hoy = FUTURO  # amanece el día programado
    assert wu.notify_released_days(box.queue) == 1
    assert len(box.enviados) == 1
    assert box.enviados[0]["to"] == ["ana@x.com"] and box.enviados[0]["count"] == 1

    out = wu.web_output(box.claims, FUTURO, box.queue)
    assert out["ready"] == 1 and out["all_done"] is True
    assert out["videos"][0]["filename"] == "a_editado.mp4"
    assert out["videos"][0]["scheduled"] is False
    assert wu.web_days_summary(box.claims, box.queue)["days"][FUTURO]["all_done"] is True

    # Idempotente: ni otra pasada ni otra visita repiten el aviso.
    assert wu.notify_released_days(box.queue) == 0
    wu.web_output(box.claims, FUTURO, box.queue)
    assert len(box.enviados) == 1


def test_el_barrido_no_avisa_de_madrugada(box):
    wu = box.wu
    box.poner_dia(FUTURO)
    box.hoy = FUTURO
    box.hora = 3
    assert wu.notify_released_days(box.queue) == 0
    assert box.enviados == []
    # Pero si el cliente entra a esa hora, sus vídeos ya están (y se le avisa).
    assert wu.web_output(box.claims, FUTURO, box.queue)["ready"] == 1
    assert len(box.enviados) == 1


def test_si_el_box_estuvo_parado_ese_dia_avisa_al_siguiente(box):
    from datetime import date, timedelta

    wu = box.wu
    box.poner_dia(FUTURO)
    despues = lambda n: (date.fromisoformat(FUTURO) + timedelta(days=n)).isoformat()
    # Dos días después ya no se repasa (no se avisa de algo viejo).
    box.hoy = despues(2)
    assert wu.notify_released_days(box.queue) == 0 and box.enviados == []
    # Al día siguiente sí: el aviso no se pierde.
    box.hoy = despues(1)
    assert wu.notify_released_days(box.queue) == 1
    assert len(box.enviados) == 1


def test_sin_aprobar_llegado_su_dia_sigue_en_revision(box):
    wu = box.wu
    box.poner_dia(FUTURO, aprobado=False)
    box.hoy = FUTURO
    out = wu.web_output(box.claims, FUTURO, box.queue)
    assert out["ready"] == 0 and out["review"] == 1 and out["all_done"] is False
    assert out["videos"][0]["in_review"] is True
    assert wu.notify_released_days(box.queue) == 1  # lo repasa, pero no avisa
    assert box.enviados == []


def test_hoy_no_cambia(box):
    wu = box.wu
    box.poner_dia(HOY)
    out = wu.web_output(box.claims, HOY, box.queue)
    assert out["ready"] == 1 and out["all_done"] is True
    assert len(box.enviados) == 1


def test_fallo_definitivo_se_ensena_antes_de_su_dia(box, monkeypatch):
    wu = box.wu
    box.poner_dia(FUTURO, status="failed", aprobado=False)
    monkeypatch.setattr(wu, "_razon_fallo", lambda job, src, dev: "No pudimos leer el archivo.")
    out = wu.web_output(box.claims, FUTURO, box.queue)
    v = out["videos"][0]
    assert v["failed_reason"] == "No pudimos leer el archivo." and v["status"] == "failed"
    assert out["all_done"] is False and box.enviados == []
