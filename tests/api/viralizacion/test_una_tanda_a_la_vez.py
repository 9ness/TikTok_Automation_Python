"""Una tanda de Viralización a la vez; la segunda espera en cola.

Hay 2 workers, así que sin esto dos tandas arrancaban EN PARALELO. No fallaba
nada, pero:

- En 4 vCPU no terminan antes: terminan las dos a la mitad de velocidad.
- Comparten el banco de ganchos. Con 27 libres, una tanda de 23 deja 4; la
  segunda los gasta, agota el banco, RECICLA y repite 19 planos que la primera
  acababa de usar.

Se prueba sobre el registro `_EXCLUSIVE_MODES` y sobre la condición de
elegibilidad, que es lo que decide si un job pendiente puede arrancar.
"""

from __future__ import annotations

from src.queue.manager import _EXCLUSIVE_MODES
from src.queue.models import Job, JobMode, JobStatus


def _elegibles(jobs: list[Job]) -> list[Job]:
    """La misma condición que usa el worker para elegir pendiente."""
    corriendo = {
        j.mode for j in jobs
        if j.status == JobStatus.RUNNING and j.mode in _EXCLUSIVE_MODES
    }
    return [
        j for j in jobs
        if j.status == JobStatus.PENDING
        and not (j.mode in _EXCLUSIVE_MODES and j.mode in corriendo)
    ]


class TestUnaTandaALaVez:
    def test_viralizacion_es_exclusivo(self):
        assert JobMode.VIRALIZACION_BATCH in _EXCLUSIVE_MODES

    def test_la_segunda_tanda_espera(self):
        corriendo = Job(mode=JobMode.VIRALIZACION_BATCH, status=JobStatus.RUNNING)
        segunda = Job(mode=JobMode.VIRALIZACION_BATCH, status=JobStatus.PENDING)
        assert _elegibles([corriendo, segunda]) == []

    def test_al_acabar_la_primera_arranca_la_segunda(self):
        primera = Job(mode=JobMode.VIRALIZACION_BATCH, status=JobStatus.COMPLETED)
        segunda = Job(mode=JobMode.VIRALIZACION_BATCH, status=JobStatus.PENDING)
        assert _elegibles([primera, segunda]) == [segunda]

    def test_no_bloquea_a_los_demas_modos(self):
        """Solo se serializa consigo mismo: montar un vídeo de otro nicho
        mientras corre una tanda tiene que seguir siendo posible."""
        tanda = Job(mode=JobMode.VIRALIZACION_BATCH, status=JobStatus.RUNNING)
        otro = Job(mode=JobMode.NICHO_POV_BOF_VIDEO, status=JobStatus.PENDING)
        assert _elegibles([tanda, otro]) == [otro]

    def test_los_clips_no_se_bloquean_con_la_tanda(self):
        """Cortar un audio largo es rápido y no compite por el banco."""
        tanda = Job(mode=JobMode.VIRALIZACION_BATCH, status=JobStatus.RUNNING)
        clips = Job(mode=JobMode.VIRALIZACION_CLIPS, status=JobStatus.PENDING)
        assert _elegibles([tanda, clips]) == [clips]
