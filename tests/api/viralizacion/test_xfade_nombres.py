"""El xfade por tandas no puede escribir sobre sus propias entradas.

Bug real: el 6 ago 2026 una tanda de 23 vídeos perdió UNO (`pablo1_9`) con
`ffmpeg ... returned non-zero exit status 234`. La orden era:

    ffmpeg -i xfade_t00.mp4 -i xfade_t01.mp4 … -> xfade_t00.mp4

o sea, la salida era también la primera entrada. ffmpeg se niega a escribir un
fichero que está leyendo.

Por qué solo ese vídeo: los tramos se montan en grupos de `XFADE_MAX_INPUTS`
(7); si salen MÁS de 7 grupos, los parciales se vuelven a agrupar, y esa
segunda vuelta generaba los MISMOS nombres (`xfade_t00`…). Hace falta pasar de
**50 tramos** para que ocurra, así que solo afecta a los vídeos largos: 22 de
23 salieron bien y el largo murió.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.viralizacion import config


def _nombres_por_nivel(n: int, out: Path, nivel: int = 0) -> list[Path]:
    """Reproduce el nombrado de `_xfade_por_tandas`, incluida la recursión."""
    tam = config.XFADE_MAX_INPUTS
    if n <= tam:
        return []
    n_grupos = -(-n // tam)
    parciales = [
        out.with_name(f"{out.stem}_n{nivel}t{g:02d}.mp4") for g in range(n_grupos)
    ]
    base, resto = divmod(n, n_grupos)
    hijos: list[Path] = []
    for g, parcial in enumerate(parciales):
        tam_grupo = base + (1 if g < resto else 0)
        hijos += _nombres_por_nivel(tam_grupo, parcial, nivel + 1)
    # La vuelta que reagrupa los parciales usa el MISMO out_path y nivel+1.
    return parciales + hijos + _nombres_por_nivel(len(parciales), out, nivel + 1)


class TestNombresDelXfade:
    @pytest.mark.parametrize("n", [8, 13, 50, 56, 120, 400])
    def test_ningun_parcial_pisa_la_salida_final(self, n: int):
        out = Path("/w/xfade.mp4")
        assert out not in _nombres_por_nivel(n, out), (
            f"con {n} tramos, un parcial se llama igual que la salida final"
        )

    @pytest.mark.parametrize("n", [50, 56, 120])
    def test_no_hay_nombres_repetidos_entre_niveles(self, n: int):
        """El caso que rompió: la segunda vuelta reusaba los nombres de la
        primera y el grupo 0 leía y escribía el mismo fichero."""
        nombres = _nombres_por_nivel(n, Path("/w/xfade.mp4"))
        assert len(nombres) == len(set(nombres)), (
            f"con {n} tramos hay parciales con el mismo nombre: "
            f"{sorted(p.name for p in nombres)}"
        )

    def test_el_caso_exacto_que_fallo(self):
        """~50 tramos: 8 grupos → se reagrupan → antes salía xfade_t00 dos
        veces, una como entrada y otra como salida."""
        nombres = _nombres_por_nivel(50, Path("/w/xfade.mp4"))
        assert len(nombres) == len(set(nombres))


class TestRedDeSeguridad:
    def test_avisa_si_la_salida_es_una_entrada(self, tmp_path: Path):
        """Aunque el nombrado ya no colisione, si vuelve a pasar tiene que
        salir un error que se entienda y no un exit code de ffmpeg."""
        from src.viralizacion.pipeline.renderer import _xfade_clips

        a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        with pytest.raises(RuntimeError, match="es también una de sus entradas"):
            _xfade_clips([a, b], [], [], a, None)
