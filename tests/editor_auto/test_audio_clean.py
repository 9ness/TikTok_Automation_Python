"""«Mejorar voz» (`audio_clean`): cadena de filtros, caídas defensivas y registro."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from src.editor_auto.config import TOOL_AUDIO_CLEAN, TOOL_POSITION_WEIGHTS
from src.editor_auto.tools import REGISTRY, ToolContext
from src.editor_auto.tools.audio_clean import (
    AudioCleanTool,
    construir_filtros,
    resolver_modelo,
)

_HAY_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
_MODELOS_PRUEBA = Path("/mnt/HC_Volume_106974679/agentes/trabajo/fable-audio/models")
_MEDIDA = {"input_i": -35.2, "input_tp": -18.4, "input_lra": 6.1, "input_thresh": -45.6,
           "target_offset": 0.3}


def _cfg(**kw):
    c = AudioCleanTool().default_config()
    c.update(kw)
    return c


def _ctx(tmp_path, logs):
    return ToolContext(user_id="u", user_name="prueba", job_id="j1", temp_folder=str(tmp_path),
                       on_log=logs.append, on_progress=lambda f, m="": None)


# --- cadena de filtros (sin ffmpeg) ------------------------------------------
def test_rnnoise_con_modelo():
    af = construir_filtros(_cfg(), True, None)
    assert af.startswith("highpass=f=80,aresample=48000,arnndn=m=")
    assert "sh.rnnn:mix=1" in af and "afftdn" not in af
    assert af.endswith("loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json")


def test_rnnoise_sin_modelo_solo_nivela():
    af = construir_filtros(_cfg(), False, None)
    assert "arnndn" not in af and "afftdn" not in af and "loudnorm" in af


def test_motor_afftdn_y_ninguno():
    assert "afftdn" in construir_filtros(_cfg(motor="afftdn"), True, None)
    af = construir_filtros(_cfg(motor="ninguno"), True, None)
    assert "afftdn" not in af and "arnndn" not in af and "loudnorm" in af
    # un motor desconocido no inventa filtros
    assert "arnndn" not in construir_filtros(_cfg(motor="otra_cosa"), True, None)


def test_todo_apagado_no_hace_nada():
    assert construir_filtros(_cfg(motor="ninguno", quitar_graves=False, nivelar=False), True, None) == ""


def test_opciones_y_orden():
    af = construir_filtros(_cfg(quitar_clics=True, compresor=True, mezcla=0.7), True, None)
    orden = [p.split("=")[0] for p in af.split(",")]
    assert orden == ["highpass", "adeclick", "aresample", "arnndn", "acompressor", "loudnorm"]
    assert ":mix=0.7" in af


def test_mezcla_y_lufs_se_acotan():
    af = construir_filtros(_cfg(mezcla=7, lufs=-3), True, None)
    assert ":mix=1," in af and "loudnorm=I=-10:" in af
    af = construir_filtros(_cfg(mezcla="x", lufs=None), True, None)
    assert ":mix=1," in af and "loudnorm=I=-16:" in af


def test_segunda_pasada_usa_la_medida():
    af = construir_filtros(_cfg(), True, _MEDIDA)
    assert "measured_I=-35.20" in af and "measured_thresh=-45.60" in af
    assert "offset=0.30:linear=true" in af and "print_format" not in af


def test_ruta_del_modelo_escapada():
    af = construir_filtros(_cfg(modelo_rnnoise="/mi carpeta/a:b.rnnn"), True, None)
    assert r"arnndn=m=/mi\ carpeta/a\:b.rnnn:mix=1" in af
    # dentro del flujo se usa el nombre simple de la copia temporal
    assert "arnndn=m=m.rnnn:" in construir_filtros(_cfg(_modelo_filtro="m.rnnn"), True, None)


def test_resolver_modelo(tmp_path):
    assert resolver_modelo(str(tmp_path / "no_existe.rnnn")) is None
    m = tmp_path / "x.rnnn"
    m.write_bytes(b"rnnoise-nu model file version 1\n")
    assert resolver_modelo(str(m)) == str(m)


# --- registro y flujo ---------------------------------------------------------
def test_registrada_con_su_peso():
    tool = REGISTRY[TOOL_AUDIO_CLEAN]
    assert TOOL_POSITION_WEIGHTS[TOOL_AUDIO_CLEAN] == 20 == tool.position_weight
    # después del cortador y antes de todo lo demás
    otros = [w for k, w in TOOL_POSITION_WEIGHTS.items() if k != TOOL_AUDIO_CLEAN]
    assert min(otros) == 10 and all(w == 10 or w > 20 for w in otros)
    d = tool.descriptor()
    assert {c["key"] for c in d.config_schema} == set(d.default_config)


def test_no_esta_en_el_flujo_por_defecto_y_se_conserva_si_la_pone_el_equipo():
    from src.editor_auto.models import ToolStep
    from src.editor_auto.services.style_mapper import build_tool_flow, conservar_pasos_del_equipo
    for estilo in (None, {}, {"arrow": {"enabled": True}}):
        assert TOOL_AUDIO_CLEAN not in [s.tool_id for s in build_tool_flow(estilo)]
    anterior = [ToolStep(tool_id="silence_cutter", enabled=True, config={}),
                ToolStep(tool_id=TOOL_AUDIO_CLEAN, enabled=True, config={"motor": "afftdn"})]
    nuevo = conservar_pasos_del_equipo(build_tool_flow({}), anterior)
    assert [s.tool_id for s in nuevo].count(TOOL_AUDIO_CLEAN) == 1
    assert nuevo[-1].config == {"motor": "afftdn"}


def test_orden_en_el_flujo():
    from src.editor_auto.models import ToolStep
    from src.editor_auto.services.flow_orchestrator import order_steps
    pasos = [ToolStep(tool_id="subs_auto", enabled=True, config={}),
             ToolStep(tool_id="vip_overlays", enabled=True, config={}),
             ToolStep(tool_id=TOOL_AUDIO_CLEAN, enabled=True, config={}),
             ToolStep(tool_id="silence_cutter", enabled=True, config={})]
    assert [s.tool_id for s in order_steps(pasos)] == [
        "silence_cutter", TOOL_AUDIO_CLEAN, "vip_overlays", "subs_auto"]


# --- con ffmpeg (vídeos de 3 s) -----------------------------------------------
pytestmark_ffmpeg = pytest.mark.skipif(not _HAY_FFMPEG, reason="sin ffmpeg")


def _video(path, audio=True, vol="0.02"):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=25:duration=3"]
    if audio:  # tono de voz flojo + ruido blanco
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=220:duration=3,volume={vol}",
                "-f", "lavfi", "-i", "anoisesrc=duration=3:amplitude=0.004:color=white",
                "-filter_complex", "[1:a][2:a]amix=inputs=2:normalize=0[a]", "-map", "0:v", "-map", "[a]",
                "-c:a", "aac", "-ar", "44100"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return str(path)


def _info(path):
    j = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,sample_rate,nb_frames:format=duration", "-of", "json", path]))
    return {s["codec_type"]: s for s in j["streams"]}, float(j["format"]["duration"])


def _lufs(path):
    err = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def _paquetes_video(path):
    return subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=size",
         "-of", "csv=p=0", path])


@pytestmark_ffmpeg
def test_video_sin_audio_se_copia(tmp_path):
    src, dst, logs = _video(tmp_path / "mudo.mp4", audio=False), str(tmp_path / "out.mp4"), []
    assert AudioCleanTool().run(input_path=src, output_path=dst, config={}, ctx=_ctx(tmp_path, logs)) == dst
    assert Path(dst).read_bytes() == Path(src).read_bytes()
    assert any("no tiene pista de audio" in m for m in logs)


@pytestmark_ffmpeg
def test_fallo_de_ffmpeg_no_rompe(tmp_path):
    src, dst, logs = _video(tmp_path / "in.mp4"), str(tmp_path / "out.mp4"), []
    malo = tmp_path / "roto.rnnn"
    malo.write_bytes(b"esto no es un modelo")
    AudioCleanTool().run(input_path=src, output_path=dst, config={"modelo_rnnoise": str(malo)},
                         ctx=_ctx(tmp_path, logs))
    assert Path(dst).read_bytes() == Path(src).read_bytes()
    assert any("sigo con el original" in m for m in logs)
    assert not list(tmp_path.glob("audio_clean_*"))  # limpia su carpeta temporal


@pytestmark_ffmpeg
def test_integracion_afftdn_nivela_sin_tocar_el_video(tmp_path):
    src, dst, logs = _video(tmp_path / "in.mp4"), str(tmp_path / "out.mp4"), []
    antes = _lufs(src)
    assert antes < -30  # el de prueba se oye muy poco
    out = AudioCleanTool().run(input_path=src, output_path=dst, config={"motor": "afftdn"},
                               ctx=_ctx(tmp_path, logs))
    assert out == dst and any("Voz mejorada (afftdn)" in m for m in logs), logs
    s0, d0 = _info(src)
    s1, d1 = _info(dst)
    assert s1["video"]["codec_name"] == s0["video"]["codec_name"] == "h264"
    assert _paquetes_video(dst) == _paquetes_video(src)  # vídeo copiado, no recodificado
    assert abs(d1 - d0) < 0.2
    assert s1["audio"]["codec_name"] == "aac" and s1["audio"]["sample_rate"] == "48000"
    assert abs(_lufs(dst) - (-16.0)) < 1.5
    assert not list(tmp_path.glob("audio_clean_*"))


@pytestmark_ffmpeg
def test_integracion_rnnoise_con_modelo_real(tmp_path):
    modelo = _MODELOS_PRUEBA / "sh.rnnn"
    if not modelo.is_file():
        pytest.skip("sin modelo rnnoise de prueba")
    src, dst, logs = _video(tmp_path / "in.mp4"), str(tmp_path / "out.mp4"), []
    AudioCleanTool().run(input_path=src, output_path=dst, config={"modelo_rnnoise": str(modelo)},
                         ctx=_ctx(tmp_path, logs))
    assert any("Voz mejorada (rnnoise)" in m for m in logs), logs
    assert _paquetes_video(dst) == _paquetes_video(src)


@pytestmark_ffmpeg
def test_sin_modelo_solo_nivela_y_avisa(tmp_path):
    src, dst, logs = _video(tmp_path / "in.mp4"), str(tmp_path / "out.mp4"), []
    AudioCleanTool().run(input_path=src, output_path=dst,
                         config={"modelo_rnnoise": str(tmp_path / "no_hay.rnnn")}, ctx=_ctx(tmp_path, logs))
    assert any("solo nivelo" in m for m in logs), logs
    assert any("Voz mejorada (sin filtro de ruido)" in m for m in logs), logs
