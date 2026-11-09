"""Comprobador técnico de vídeo: juicios (puros) y una pasada real con ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from src.comprobador_video import tecnico as c
from src.comprobador_video.__main__ import main

HAY_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
con_ffmpeg = pytest.mark.skipif(not HAY_FFMPEG, reason="sin ffmpeg en este equipo")


# --- formato ---------------------------------------------------------------
def test_formato_bueno():
    assert c.juzgar_formato(1080, 1920, 12.0).veredicto == c.PASA


@pytest.mark.parametrize("ancho, alto, duracion, esperado", [
    (1920, 1080, 12.0, c.FALLA),   # horizontal
    (1080, 1080, 12.0, c.FALLA),   # cuadrado
    (1080, 1440, 12.0, c.FALLA),   # 3:4: vertical pero no 9:16
    (720, 1280, 12.0, c.DUDAS),    # 9:16 a otra resolución
    (1080, 1920, 0.2, c.FALLA),    # montaje roto
    (0, 0, 12.0, c.FALLA),         # sin pista de vídeo
])
def test_formato_malo(ancho, alto, duracion, esperado):
    assert c.juzgar_formato(ancho, alto, duracion).veredicto == esperado


# --- bandas ----------------------------------------------------------------
def test_bandas_sin_bandas():
    assert c.juzgar_bandas((1080, 1920, 0, 0), 1080, 1920).veredicto == c.PASA
    # Un par de píxeles de borde no son una banda.
    assert c.juzgar_bandas((1076, 1916, 2, 2), 1080, 1920).veredicto == c.PASA


def test_bandas_3_4_dentro_de_9_16_falla_y_dice_donde():
    r = c.juzgar_bandas((1080, 1440, 0, 240), 1080, 1920)
    assert r.veredicto == c.FALLA
    assert "arriba y abajo" in r.detalle and "1080x1440" in r.detalle
    assert r.valor["falta_pct"] == 25.0


def test_bandas_a_los_lados():
    r = c.juzgar_bandas((810, 1920, 135, 0), 1080, 1920)
    assert r.veredicto == c.FALLA and "a los lados" in r.detalle


def test_bandas_finas_son_duda_y_sin_crop_tambien():
    assert c.juzgar_bandas((1080, 1870, 0, 25), 1080, 1920).veredicto == c.DUDAS
    assert c.juzgar_bandas(None, 1080, 1920).veredicto == c.DUDAS


def test_leer_crop_se_queda_con_el_ultimo():
    salida = "x crop=1080:1900:0:10\n[Parsed_cropdetect] t:3 crop=1080:1440:0:240\n"
    assert c.leer_crop(salida) == (1080, 1440, 0, 240)
    assert c.leer_crop("nada") is None


# --- movimiento ------------------------------------------------------------
def test_movimiento_bueno():
    r = c.juzgar_movimiento([3.0] * 50 + [2.5] * 50, clips=2)
    assert r.veredicto == c.PASA and r.valor["por_clip"] == [3.0, 2.5]


def test_movimiento_un_clip_parado_aunque_la_media_sea_buena():
    """El caso sancionado: un clip vivo tapa a otro casi quieto."""
    r = c.juzgar_movimiento([4.0] * 50 + [0.6] * 50, clips=2)
    assert r.veredicto == c.DUDAS
    assert "clip 2" in r.detalle


def test_movimiento_estatico_falla():
    r = c.juzgar_movimiento([0.9] * 100, clips=2)
    assert r.veredicto == c.FALLA and "estático" in r.detalle.lower()


def test_movimiento_sin_fotogramas_no_revienta():
    assert c.juzgar_movimiento([], clips=2).veredicto == c.DUDAS


def test_partir_reparte_en_clips():
    assert c.partir([1, 1, 3, 3, 5, 5], 3) == [1, 3, 5]
    assert c.partir([2.0], 4) == [2.0]          # más clips que fotogramas
    assert c.partir([1, 2, 3], 0) == [2.0]      # 0 clips = uno


# --- audio -----------------------------------------------------------------
def test_audio_con_voz():
    assert c.juzgar_audio(True, -1.4, -12.2).veredicto == c.PASA


def test_audio_sin_pista_es_duda_en_mudo_y_fallo_con_voz():
    assert c.juzgar_audio(False, None, None).veredicto == c.DUDAS
    assert c.juzgar_audio(False, None, None, con_voz=True).veredicto == c.FALLA


def test_audio_en_silencio_y_muy_bajo():
    assert c.juzgar_audio(True, -91.0, -91.0).veredicto == c.DUDAS
    assert c.juzgar_audio(True, -91.0, -91.0, con_voz=True).veredicto == c.FALLA
    assert c.juzgar_audio(True, -20.0, -40.0).veredicto == c.DUDAS


def test_leer_volumen():
    salida = "[Parsed_volumedetect_0] mean_volume: -12.2 dB\n[Parsed_volumedetect_0] max_volume: -1.4 dB\n"
    assert c.leer_volumen(salida) == (-1.4, -12.2)
    assert c.leer_volumen("mean_volume: -inf dB\nmax_volume: -inf dB") == (-91.0, -91.0)
    assert c.leer_volumen("") == (None, None)


# --- metadatos -------------------------------------------------------------
def test_metadatos_limpios():
    tags = {"major_brand": "isom", "minor_version": "512", "compatible_brands": "isomiso2",
            "handler_name": "VideoHandler", "vendor_id": "[0][0][0][0]", "language": "und"}
    assert c.juzgar_metadatos(tags).veredicto == c.PASA


def test_metadatos_con_firma():
    r = c.juzgar_metadatos({"major_brand": "isom", "encoder": "Lavf61.7.103", "comment": "Made with X"})
    assert r.veredicto == c.DUDAS
    assert set(r.valor) == {"encoder", "comment"} and "limpiar_metadatos" in r.detalle


# --- sonda -----------------------------------------------------------------
def test_leer_sonda_junta_tags_y_gira_el_video_del_movil():
    doc = {
        "format": {"duration": "12.5", "size": "7160000", "tags": {"major_brand": "isom", "encoder": "Lavf"}},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
             "avg_frame_rate": "30/1", "tags": {"handler_name": "VideoHandler"},
             "side_data_list": [{"rotation": -90}]},
            {"codec_type": "audio", "codec_name": "aac", "tags": {"language": "und"}},
        ],
    }
    s = c.leer_sonda(doc)
    assert (s["ancho"], s["alto"]) == (1080, 1920)      # grabado en vertical
    assert s["duracion"] == 12.5 and s["audio"] and s["mb"] == 7.16
    assert s["tags"] == {"major_brand": "isom", "encoder": "Lavf", "handler_name": "VideoHandler", "language": "und"}


def test_leer_sonda_sin_video():
    s = c.leer_sonda({"format": {}, "streams": [{"codec_type": "audio"}]})
    assert s["ancho"] == 0 and s["audio"]


# --- informe ---------------------------------------------------------------
def test_el_informe_se_queda_con_lo_peor():
    inf = c.Informe(ruta="x.mp4")
    inf.anadir(c.Comprobacion("a", c.PASA, ""))
    inf.anadir(c.Comprobacion("b", c.FALLA, ""))
    inf.anadir(c.Comprobacion("c", c.DUDAS, ""))
    assert inf.veredicto == c.FALLA
    assert [x.clave for x in inf.fallos()] == ["b", "c"]
    assert inf.como_dict()["comprobaciones"][1]["veredicto"] == c.FALLA


def test_no_existe():
    with pytest.raises(c.ErrorComprobador):
        c.comprobar("/no/existe.mp4")


# --- con ffmpeg de verdad --------------------------------------------------
def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", *args], check=True, timeout=120)


@pytest.fixture(scope="module")
def videos(tmp_path_factory):
    d = tmp_path_factory.mktemp("videos")
    x264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    # Ruido: se mueve de sobra; con tono y sin metadatos.
    _ffmpeg("-f", "lavfi", "-i", "nullsrc=s=1080x1920:r=12:d=2,geq=random(1)*255:128:128",
            "-f", "lavfi", "-i", "sine=f=440:d=2", *x264, "-c:a", "aac", "-shortest",
            "-map_metadata", "-1", str(d / "sucio.mp4"))
    _ffmpeg("-i", str(d / "sucio.mp4"), "-map_metadata", "-1", "-map_chapters", "-1",
            "-fflags", "+bitexact", "-c", "copy", str(d / "bien.mp4"))
    # 3:4 con bandas dentro de un 9:16, gris parado, mudo y con comentario.
    _ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=1080x1440:r=12:d=2", "-vf", "pad=1080:1920:0:240:black",
            *x264, "-an", "-metadata", "comment=hecho con X", str(d / "malo.mp4"))
    (d / "roto.mp4").write_bytes(b"esto no es un video")
    return d


@con_ffmpeg
def test_video_bueno_pasa(videos):
    inf = c.comprobar(videos / "bien.mp4")
    assert inf.veredicto == c.PASA, [(x.clave, x.detalle) for x in inf.fallos()]
    assert [x.clave for x in inf.comprobaciones] == ["formato", "bandas", "movimiento", "audio", "metadatos"]
    assert inf.datos["audio"] and "tags" not in inf.datos


@con_ffmpeg
def test_video_sin_limpiar_es_duda_solo_por_metadatos(videos):
    inf = c.comprobar(videos / "sucio.mp4")
    assert [x.clave for x in inf.fallos()] == ["metadatos"] and inf.veredicto == c.DUDAS


@con_ffmpeg
def test_video_malo_dice_todo_lo_que_falla(videos):
    inf = c.comprobar(videos / "malo.mp4")
    por = {x.clave: x.veredicto for x in inf.comprobaciones}
    assert inf.veredicto == c.FALLA
    assert por == {"formato": c.PASA, "bandas": c.FALLA, "movimiento": c.FALLA,
                   "audio": c.DUDAS, "metadatos": c.DUDAS}
    assert c.comprobar(videos / "malo.mp4", con_voz=True).comprobaciones[3].veredicto == c.FALLA


@con_ffmpeg
def test_fichero_que_no_es_video(videos):
    with pytest.raises(c.ErrorComprobador):
        c.comprobar(videos / "roto.mp4")


@con_ffmpeg
def test_cli_codigos_de_salida_y_json(videos, capsys):
    assert main([str(videos / "bien.mp4")]) == 0
    assert "pasa" in capsys.readouterr().out
    assert main([str(videos / "bien.mp4"), str(videos / "malo.mp4")]) == 1
    assert "bandas" in capsys.readouterr().out
    assert main(["--json", str(videos / "malo.mp4"), str(videos / "roto.mp4")]) == 2
    doc = json.loads(capsys.readouterr().out)
    assert [v["veredicto"] for v in doc] == ["falla", "error"]
