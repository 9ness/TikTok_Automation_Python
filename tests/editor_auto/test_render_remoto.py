"""Render en el PC de casa con respaldo local (ssh falso: el «PC» es una carpeta)."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess

import pytest

from src.editor_auto.services import render_remoto as rr

FFMPEG = shutil.which("ffmpeg")

SSH_FALSO = """#!/bin/sh
# Imita a ssh: quita las opciones -o y el host y ejecuta el resto en local.
echo "$*" >> "$(dirname "$0")/llamadas.log"
while [ $# -gt 0 ]; do case "$1" in -o) shift 2;; *) break;; esac; done
shift
exec sh -c "$*"
"""

SSH_CAIDO = """#!/bin/sh
echo "ssh: connect to host 100.125.167.31 port 22: Connection timed out" >&2
exit 255
"""


def _script(carpeta, nombre, texto):
    p = carpeta / nombre
    p.write_text(texto)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


@pytest.fixture
def pc(tmp_path, monkeypatch):
    """Entorno con el remoto encendido y un ssh falso que funciona."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    remoto = tmp_path / "pc_casa"
    monkeypatch.setenv("EDITOR_RENDER_REMOTO", "1")
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_SSH", _script(bin_dir, "ssh", SSH_FALSO))
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_DIR", str(remoto))
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_FFMPEG", os.path.dirname(FFMPEG or "/usr/bin/ffmpeg"))
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_MIN_S", "0")
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    rr._reset_para_tests()
    yield {"bin": bin_dir, "remoto": remoto, "tmp": tmp_path}
    rr._reset_para_tests()


def _video(ruta, segundos=2):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"testsrc=s=160x284:d={segundos}:r=10",
                    "-f", "lavfi", "-i", f"sine=f=440:d={segundos}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
                    str(ruta)], check=True)
    return str(ruta)


def _cmd(entrada, salida):
    return ["ffmpeg", "-y", "-i", entrada,
            "-filter_complex", "[0:v]trim=0:1,setpts=PTS-STARTPTS[v];"
                               "[0:a]atrim=0:1,asetpts=PTS-STARTPTS[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", salida]


# ── Reescritura del comando ───────────────────────────────────────────────────
def test_preparar_cambia_rutas_y_rechaza_ficheros_sueltos(tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    prep = rr.preparar(_cmd(str(src), str(tmp_path / "o.mp4")), "/r/j1")
    assert prep is not None
    cmd, entradas, salida = prep
    assert entradas == {str(src): "/r/j1/in0.mp4"}
    assert cmd[cmd.index("-i") + 1] == "/r/j1/in0.mp4" and cmd[-1] == "/r/j1/out.mp4"
    assert salida == str(tmp_path / "o.mp4")
    # Un filtro con un fichero local (subtítulos) no se puede mover.
    sub = _cmd(str(src), str(tmp_path / "o.mp4"))
    sub[sub.index("-filter_complex") + 1] = f"subtitles={tmp_path}/s.ass"
    assert rr.preparar(sub, "/r/j") is None
    # Entrada que no existe, salida que no es mp4 o no es ffmpeg → no.
    assert rr.preparar(_cmd("/no/existe.mp4", str(tmp_path / "o.mp4")), "/r/j") is None
    assert rr.preparar(_cmd(str(src), str(tmp_path / "o.wav")), "/r/j") is None
    assert rr.preparar(["ffprobe", "-i", str(src), "o.mp4"], "/r/j") is None


def test_cambiar_a_nvenc_quita_opciones_de_x264():
    cmd = rr.cambiar_a_nvenc(_cmd("/a.mp4", "/o.mp4"))
    assert "libx264" not in cmd and "-crf" not in cmd and "medium" not in cmd
    i = cmd.index("h264_nvenc")
    assert cmd[i - 1] == "-c:v" and cmd.count("-pix_fmt") == 1
    assert cmd[-1] == "/o.mp4" and "-c:a" in cmd
    assert rr.cambiar_a_nvenc(["ffmpeg", "-c:v", "copy", "o.mp4"]) == ["ffmpeg", "-c:v", "copy", "o.mp4"]


def test_apagado_por_defecto(monkeypatch, tmp_path):
    monkeypatch.delenv("EDITOR_RENDER_REMOTO", raising=False)
    llamado = []
    assert rr.intentar(["ffmpeg", "-i", "x", "o.mp4"], ejecutar=llamado.append) is False
    assert not llamado


def test_video_corto_no_compensa(pc, monkeypatch, tmp_path):
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_MIN_S", "20")
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    assert rr.intentar(_cmd(str(src), str(tmp_path / "o.mp4")), ejecutar=lambda c: None,
                       duracion_s=8) is False
    assert not (pc["bin"] / "llamadas.log").exists()  # ni siquiera prueba la conexión


def test_disponible_con_cache(pc):
    assert rr.disponible() == (True, False)  # el contenedor no tiene GPU → CPU
    n = (pc["bin"] / "llamadas.log").read_text().count("\n")
    assert rr.disponible() == (True, False)
    assert (pc["bin"] / "llamadas.log").read_text().count("\n") == n  # sin otro ssh


def test_pc_caido_cuenta_como_no_disponible(pc, monkeypatch):
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_SSH", _script(pc["bin"], "ssh_caido", SSH_CAIDO))
    assert rr.disponible() == (False, False)


# ── De punta a punta con el ejecutor real del cortador ────────────────────────
@pytest.mark.skipif(not FFMPEG, reason="sin ffmpeg")
def test_render_en_remoto_de_punta_a_punta(pc, tmp_path):
    from src.editor_auto.tools import silence_cutter as sc
    entrada = _video(tmp_path / "cliente.mp4")
    salida = str(tmp_path / "final.mp4")
    progreso, logs = [], []
    sc._run_ffmpeg_with_progress(_cmd(entrada, salida), on_progress=progreso.append,
                                 total_ms=1000, log=logs.append)
    assert os.path.getsize(salida) > 1024
    assert progreso and progreso[-1] == 1.0
    assert any("PC de casa (CPU)" in m for m in logs), logs
    llamadas = (pc["bin"] / "llamadas.log").read_text()
    assert "cat >" in llamadas and "out.mp4" in llamadas and "rm -rf" in llamadas
    assert not any(pc["remoto"].iterdir())  # carpeta de trabajo borrada
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", salida]))
    assert dur == pytest.approx(1.0, abs=0.15)


@pytest.mark.skipif(not FFMPEG, reason="sin ffmpeg")
def test_pc_caido_renderiza_en_local(pc, monkeypatch, tmp_path):
    from src.editor_auto.tools import silence_cutter as sc
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_SSH", _script(pc["bin"], "ssh_caido", SSH_CAIDO))
    entrada = _video(tmp_path / "cliente.mp4")
    salida = str(tmp_path / "final.mp4")
    sc._run_ffmpeg_with_progress(_cmd(entrada, salida), on_progress=lambda f: None,
                                 total_ms=1000, log=lambda m: None)
    assert os.path.getsize(salida) > 1024


@pytest.mark.skipif(not FFMPEG, reason="sin ffmpeg")
def test_ffmpeg_remoto_falla_y_se_hace_en_local(pc, monkeypatch, tmp_path):
    """El PC responde pero su ffmpeg revienta a mitad: respaldo local y no
    se vuelve a intentar enseguida."""
    from src.editor_auto.tools import silence_cutter as sc
    roto = pc["tmp"] / "ffmpeg_roto"
    roto.mkdir()
    _script(roto, "ffmpeg", "#!/bin/sh\ncase \"$*\" in *nvenc*) echo NVENC;; esac\n"
                            "echo 'Error: out of memory' >&2; exit 1\n")
    monkeypatch.setenv("EDITOR_RENDER_REMOTO_FFMPEG", str(roto))
    rr._ESTADO.update(ts=__import__("time").time(), ok=True, nvenc=False)  # ya «comprobado»
    entrada = _video(tmp_path / "cliente.mp4")
    salida = str(tmp_path / "final.mp4")
    logs = []
    sc._run_ffmpeg_with_progress(_cmd(entrada, salida), on_progress=lambda f: None,
                                 total_ms=1000, log=logs.append)
    assert os.path.getsize(salida) > 1024
    assert any("se hace en el VPS" in m for m in logs)
    assert rr._ESTADO["ok"] is False
    assert not any(pc["remoto"].iterdir())
