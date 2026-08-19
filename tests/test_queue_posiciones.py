"""El puesto en la cola que se le enseña a cada uno.

La cola es ÚNICA y compartida entre las tres cuentas, pero cada persona solo
ve lo suyo. Por eso el puesto NO se puede contar en la interfaz: Ana vería su
vídeo "el primero" teniendo veinte por delante. Se calcula aquí, sobre la lista
entera, y luego viaja con cada job.
"""

from __future__ import annotations

import tempfile

import pytest

from src.queue import manager as queue_manager
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


@pytest.fixture
def cola() -> JobQueue:
    # `readonly=True`: no arranca hilos trabajadores. Instanciar una JobQueue
    # normal en un test se llevaría por delante jobs de verdad (ver el aviso de
    # `leer_jobs` en el manager).
    return JobQueue(persist_dir=tempfile.mkdtemp(), readonly=True)


def _encolar(cola: JobQueue, modo: JobMode, quien: str, **params):
    return cola.enqueue(modo, title=quien, params=params, enqueued_by=quien)


def test_el_puesto_es_de_la_cola_entera_no_de_la_de_cada_uno(cola: JobQueue):
    mio1 = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")
    de_ana = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ana")
    mio2 = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")

    puestos = cola.posiciones_pendientes()

    # Ana tiene UN trabajo, pero no es el número 1: hay uno mío delante.
    assert puestos[mio1.id] == 1
    assert puestos[de_ana.id] == 2
    assert puestos[mio2.id] == 3
    assert len(puestos) == 3


def test_al_arrancar_uno_los_de_detras_adelantan(cola: JobQueue):
    primero = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")
    segundo = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ana")

    primero.status = JobStatus.RUNNING
    puestos = cola.posiciones_pendientes()

    # El que corre ya no está esperando, así que sale del recuento.
    assert primero.id not in puestos
    assert puestos[segundo.id] == 1
    assert len(puestos) == 1


def test_las_ediciones_de_cliente_van_las_ultimas(cola: JobQueue):
    """Es la misma regla que aplica el worker al elegir: los trabajos de admin
    se cogen antes que las ediciones de clientes de la web, aunque estas se
    hayan encolado primero. El número tiene que decir lo mismo."""
    del_cliente = _encolar(
        cola, JobMode.EDITOR_AUTO, "cliente", output_subdir="2026-08-19",
    )
    mio = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")

    puestos = cola.posiciones_pendientes()

    assert puestos[mio.id] == 1
    assert puestos[del_cliente.id] == 2


def test_sin_pendientes_no_hay_puestos(cola: JobQueue):
    job = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")
    job.status = JobStatus.RUNNING
    assert cola.posiciones_pendientes() == {}


class TestHistorial:
    """El histórico no se limpiaba solo: cada trabajo acabado se quedaba para
    siempre, y esa lista se reescribe entera en disco en cada cambio de estado
    y se recorre entera cada segundo por cada pestaña abierta."""

    def test_se_queda_con_los_ultimos_y_tira_los_viejos(self, cola, monkeypatch):
        monkeypatch.setattr(queue_manager, "HISTORIAL_MAX", 5)
        for i in range(12):
            j = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")
            j.title = f"t{i}"
            j.status = JobStatus.COMPLETED
            j.finished_at = 1000 + i

        with cola._lock:
            cola._save_state_locked()

        quedan = [j.title for j in cola.get_all()]
        assert quedan == ["t7", "t8", "t9", "t10", "t11"]

    def test_no_toca_lo_pendiente_ni_lo_que_corre(self, cola, monkeypatch):
        monkeypatch.setattr(queue_manager, "HISTORIAL_MAX", 2)
        for i in range(6):
            j = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ness")
            j.status = JobStatus.COMPLETED
            j.finished_at = 1000 + i
        pendiente = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "ana")
        corriendo = _encolar(cola, JobMode.NICHO_POV_BOF_LARGO_VIDEO, "mauro")
        corriendo.status = JobStatus.RUNNING

        with cola._lock:
            cola._save_state_locked()

        ids = {j.id for j in cola.get_all()}
        assert pendiente.id in ids
        assert corriendo.id in ids
        assert len(ids) == 4  # 2 del histórico + los dos vivos
