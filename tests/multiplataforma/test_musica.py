"""Música de fondo en los vídeos mudos de Mis tandas (ffmpeg real, clips sintéticos)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import zoneinfo
from pathlib import Path

import pytest

from src.multiplataforma import config
from src.multiplataforma.models import CuentaDestino
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import musica, tandas

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                                reason="sin ffmpeg")

TZ = zoneinfo.ZoneInfo("Europe/Madrid")
AHORA = dt.datetime(2026, 10, 8, 10, 0, tzinfo=TZ).timestamp()
SHEIN = "https://onelink.shein.com/17/4z8x1abc"


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _video(path: Path, segundos: float = 2.0, voz: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    entrada = ["-f", "lavfi", "-i", f"testsrc=size=180x320:rate=25:duration={segundos}"]
    if voz:
        entrada += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={segundos}"]
    _ff(*entrada, "-c:v", "libx264", "-pix_fmt", "yuv420p", *(["-c:a", "aac", "-shortest"] if voz else []),
        str(path))
    return path


def _pista(path: Path, freq: int, segundos: float = 12.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ff("-f", "lavfi", "-i", f"sine=frequency={freq}:duration={segundos}", "-c:a", "libmp3lame", str(path))
    return path


def _streams(path: Path) -> list[str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    return out.split()


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    base = tmp_path / "_musica"
    _pista(base / "lofi_otono" / "a.mp3", 440)
    _pista(base / "lofi_otono" / "b.mp3", 550)
    _pista(base / "country_western" / "c.mp3", 660)
    monkeypatch.setenv("MULTIPLATAFORMA_MUSICA_DIR", str(base))
    monkeypatch.setenv("MULTIPLATAFORMA_MUSICA_TRABAJO", str(tmp_path / "trabajo"))
    return base


@pytest.mark.parametrize("busqueda,estilo", [
    ("autumn lofi", "lofi_otono"), ("cozy autumn", "lofi_otono"), ("coffee shop jazz", "jazz_cafe"),
    ("bossa nova cafe", "bossa_lounge"), ("brazilian jazz chill", "bossa_lounge"),
    ("chanson française", "jazz_cafe"), ("retro 60s pop", "retro_vintage"), ("old vinyl aesthetic", "retro_vintage"),
    ("western aesthetic", "country_western"), ("cowboy aesthetic song", "country_western"),
    ("slow blues aesthetic", "blues_vintage"), ("vintage rock ballad", "blues_vintage"),
    ("road trip indie folk", "folk_carretera"), ("indie folk acoustic", "folk_acustico"),
    ("deep house fashion", "house_fashion"), ("house music get ready", "house_fashion"),
    ("pop dance trend", "pop_outfit"), ("outfit of the day song", "pop_outfit"),
    ("dreamy indie pop", "dream_pop"), ("late night rnb", "rnb_suave"), ("boom bap chill", "hiphop_chill"),
    ("70s soul aesthetic", "soul_funk_70s"), ("algo raro sin nada", config.MUSICA_ESTILO_NEUTRO),
])
def test_elegir_estilo(busqueda, estilo):
    assert musica.elegir_estilo({"busqueda": busqueda}) == estilo


def test_elegir_estilo_usa_estilo_y_alternativas_y_tolera_vacio():
    assert musica.elegir_estilo({"busqueda": "", "estilo": "country y folk vintage"}) == "country_western"
    assert musica.elegir_estilo({"alternativas": ["lofi jazz"]}) in ("lofi_otono", "jazz_cafe")
    assert musica.elegir_estilo(None) == config.MUSICA_ESTILO_NEUTRO
    assert musica.elegir_estilo("western aesthetic") == "country_western"


def test_mudo_sale_con_musica_y_el_original_no_se_toca(banco, tmp_path):
    v = _video(tmp_path / "ana" / "vestido.mp4", 2.0)
    antes = v.read_bytes()
    r = musica.con_musica(str(v), {"busqueda": "autumn lofi"}, "ama_shop")
    assert r and r["estilo"] == "lofi_otono" and r["pista"] == "a.mp3" and not r["reutilizada"]
    copia = Path(r["path"])
    assert copia.parent == tmp_path / "trabajo" / "ama_shop"
    assert sorted(_streams(copia)) == sorted(["h264,video", "aac,audio"])
    assert abs(musica.duracion(copia) - 2.0) < 0.2
    assert v.read_bytes() == antes
    meta = json.loads(copia.with_suffix(".json").read_text("utf-8"))
    assert meta["original"] == str(v) and meta["busqueda"] == "autumn lofi"
    # Repetir reutiliza la copia (no rota ni rehace).
    r2 = musica.con_musica(str(v), {"busqueda": "autumn lofi"}, "ama_shop")
    assert r2["path"] == r["path"] and r2["reutilizada"] and r2["pista"] == "a.mp3"


def test_rota_pistas_por_cuenta(banco, tmp_path):
    p1 = musica.con_musica(str(_video(tmp_path / "v1.mp4", 1.0)), {"busqueda": "lofi"}, "ama_shop")["pista"]
    p2 = musica.con_musica(str(_video(tmp_path / "v2.mp4", 1.0)), {"busqueda": "lofi"}, "ama_shop")["pista"]
    p3 = musica.con_musica(str(_video(tmp_path / "v3.mp4", 1.0)), {"busqueda": "lofi"}, "otra")["pista"]
    assert p1 != p2 and p3 == "a.mp3"


def test_estilo_sin_carpeta_cae_al_neutro(banco, tmp_path):
    r = musica.con_musica(str(_video(tmp_path / "v.mp4", 1.0)), {"busqueda": "deep house fashion"}, "ama_shop")
    assert r and Path(banco / "lofi_otono" / r["pista"]).is_file()


def test_con_voz_o_sin_banco_o_roto_va_tal_cual(banco, tmp_path, monkeypatch):
    assert musica.con_musica(str(_video(tmp_path / "voz.mp4", 1.0, voz=True)), {"busqueda": "lofi"}, "a") is None
    roto = tmp_path / "roto.mp4"
    roto.write_bytes(b"v")
    assert musica.con_musica(str(roto), {"busqueda": "lofi"}, "a") is None
    assert musica.con_musica(str(tmp_path / "no_existe.mp4"), None, "a") is None
    monkeypatch.setenv("MULTIPLATAFORMA_MUSICA_DIR", str(tmp_path / "vacio"))
    assert musica.con_musica(str(_video(tmp_path / "m.mp4", 1.0)), {"busqueda": "lofi"}, "a") is None


def test_encolar_usa_la_copia_con_musica_solo_en_mudos(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("DRIVE_MOUNT_ROOT", str(tmp_path))
    monkeypatch.setenv("MULTIPLATAFORMA_DRIVE_ROOT", str(tmp_path / config.DRIVE_SUBDIR))
    base = tmp_path / config.AI_PRO_SUBDIR / "Moda_Mujer" / "videos"
    mudo = _video(base / "botas.mp4", 1.5)
    hablado = _video(base / "habla.mp4", 1.5, voz=True)
    filas = []
    for i, (v, titulo, mus) in enumerate([(mudo, "Botas", {"busqueda": "western aesthetic"}),
                                          (hablado, "Gabardina", None)]):
        filas.append({"id": f"mm|r|C1|{i}|", "nicho": "multimodo", "source": "r", "carpeta": "C1",
                      "producto": str(i), "titulo": titulo, "tienda": "T", "caption": "Mira", "uploaded": True,
                      "uploaded_at": float(i + 1), "video_path": str(v), "video_listo_at": 1.0, "musica": mus})
    from src.mis_tandas import fuentes, servicio

    monkeypatch.setattr(fuentes, "todas", lambda u: ([], list(filas), []))
    monkeypatch.setattr(servicio, "ocultos", lambda u: set())
    cuentas_repo.guardar(CuentaDestino(slug="ama_shop", nombre="Ama Shop", dueno="ana"))
    for f in filas:
        tandas.guardar_enlace("ama_shop", tandas.producto_key(f), shein=SHEIN)

    inf = tandas.encolar("ama_shop", ahora=AHORA)
    assert [e["musica"] for e in inf["encoladas"]] == ["country_western/c.mp3", ""]
    pubs = [publicaciones_repo.get(e["id"]) for e in inf["encoladas"]]
    assert pubs[0].video_path.startswith(str(tmp_path / "trabajo")) and "aac,audio" in _streams(Path(pubs[0].video_path))
    assert pubs[1].video_path == str(hablado)
    # Idempotente: el SET guarda el ORIGINAL.
    assert tandas.encolar("ama_shop", ahora=AHORA)["total"] == 0
