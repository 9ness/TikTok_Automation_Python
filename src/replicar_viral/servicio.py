"""Replicar un vídeo viral con un producto nuestro (Programa 4).

Flujo (clase del 30 sep 2026, ver `docs/clases/2026-09-30_clase_miercoles.md`):

1. El vídeo de referencia: por enlace de TikTok (se baja con tikwm, porque
   TikTok bloquea la IP del VPS a yt-dlp) o subido a mano.
2. Se comprime (720p, máx. 60 s) para mandarlo entero a Gemini: ve imagen Y
   audio, así saca la transcripción y las escenas en la misma llamada (lo que en
   la clase hacían Tagshop + Submagic + DeepSeek).
3. Gemini lo adapta a NUESTRO formato con la ficha y la foto limpia del producto
   (catálogo del POV BOF): guion de ~16 s para Fish + imagen inicial y prompt de
   cada uno de los DOS clips mudos de 8 s.

No genera ni imágenes ni vídeos: solo texto (una llamada de Gemini Flash). Lo
generado se guarda en Redis (`replicar_viral:<id>`) para volver a verlo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import requests

PROMPT = Path(__file__).parent / "prompts" / "replicar.md"
MODELO = "gemini-2.5-flash"
CLAVE = "replicar_viral:{id}"
INDICE = "replicar_viral:indice:{usuario}"
MAX_S = 60


class ErrorReplica(Exception):
    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


def _redis():
    from src.viralizacion.repos.redis_base import get_viralizacion_redis

    return get_viralizacion_redis()


# ---------------------------------------------------------------------------
# Vídeo de referencia
# ---------------------------------------------------------------------------
def descargar_tiktok(url: str, destino: Path) -> dict:
    """Baja el vídeo SIN marca de agua con tikwm. Devuelve sus datos."""
    url = (url or "").strip()
    if "tiktok.com" not in url:
        raise ErrorReplica("Pega un enlace de TikTok (tiktok.com/…).")
    try:
        r = requests.get("https://www.tikwm.com/api/", params={"url": url, "hd": 1}, timeout=40)
        d = r.json()
    except Exception as e:  # noqa: BLE001
        raise ErrorReplica(f"No se pudo consultar el vídeo: {e}", status=502) from e
    datos = d.get("data") or {}
    enlace = datos.get("hdplay") or datos.get("play")
    if d.get("code") != 0 or not enlace:
        raise ErrorReplica(f"TikTok no devolvió el vídeo ({d.get('msg') or 'sin enlace'}). Súbelo a mano.", status=502)
    if datos.get("images"):
        raise ErrorReplica("Ese enlace es un carrusel de fotos, no un vídeo.")
    with requests.get(enlace, stream=True, timeout=120) as v:
        v.raise_for_status()
        with open(destino, "wb") as f:
            for trozo in v.iter_content(1 << 20):
                f.write(trozo)
    return {
        "titulo": datos.get("title") or "",
        "autor": (datos.get("author") or {}).get("unique_id") or "",
        "vistas": datos.get("play_count") or 0,
        "duracion_s": datos.get("duration") or 0,
    }


def _comprimir(origen: Path, destino: Path) -> Path:
    """720 de alto como mucho, ≤60 s y bitrate bajo: Gemini lo recibe en línea
    (tope de ~20 MB por petición) y para entender el vídeo sobra."""
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(origen), "-t", str(MAX_S),
        "-vf", "scale=-2:'min(720,ih)'", "-r", "24",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
        "-c:a", "aac", "-b:a", "64k", str(destino),
    ]
    subprocess.run(cmd, check=True, timeout=300)
    return destino


# ---------------------------------------------------------------------------
# Nuestro producto (catálogo del POV BOF)
# ---------------------------------------------------------------------------
def _producto(source: str, folder: str, producto: str, usuario: str, carpeta_tmp: Path) -> tuple[dict, Path | None]:
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    textos = pov_repo.get_product(source, folder, producto, usuario) or {}
    if not textos.get("titulo"):
        raise ErrorReplica("Ese producto no tiene textos todavía: pásale «Textos» en su nicho antes.")
    foto: Path | None = None
    try:
        fotos = [drive_client.probe_dimensions(x) for x in drive_client.list_photos(source, folder)]
        par = next((p for p in photo_pairing.pair_folder(fotos) if p["producto"] == str(producto)), None)
        limpia = (par or {}).get("clean") or (par or {}).get("titled")
        if limpia:
            suf = Path(limpia.get("name", "")).suffix.lower() or ".jpg"
            foto = Path(shutil.copy(drive_client.fetch_photo(limpia["id"], suffix=suf), carpeta_tmp / f"producto{suf}"))
    except Exception:  # noqa: BLE001 — sin foto, Gemini se guía por la ficha
        foto = None
    return textos, foto


def _ficha(textos: dict) -> str:
    campos = ("titulo", "titulo_tiktok_completo", "tienda", "precio", "caption", "descripcion", "notas")
    lineas = [f"- {c}: {textos[c]}" for c in campos if textos.get(c)]
    return "\n".join(lineas) or "- (sin ficha)"


# ---------------------------------------------------------------------------
# Análisis + adaptación
# ---------------------------------------------------------------------------
def replicar(
    usuario: str, *, source: str, folder: str, producto: str,
    url: str = "", fichero: Path | None = None,
) -> dict:
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.api.gemini import generate_text

    usuario = usuario or "ness"
    tmp = Path(tempfile.mkdtemp(prefix="replica_"))
    try:
        origen = tmp / "original.mp4"
        meta: dict = {}
        if fichero is not None:
            shutil.copy(fichero, origen)
        elif url:
            meta = descargar_tiktok(url, origen)
        else:
            raise ErrorReplica("Falta el enlace de TikTok o el vídeo.")
        video = _comprimir(origen, tmp / "ref.mp4")
        textos, foto = _producto(source, folder, producto, usuario, tmp)

        sistema = PROMPT.read_text(encoding="utf-8")
        if sistema.startswith("<!--"):
            sistema = sistema.split("-->", 1)[1].strip()
        mensaje = (
            "VÍDEO DE REFERENCIA: el vídeo adjunto"
            + (f" (de @{meta['autor']}, {meta['vistas']} vistas: «{meta['titulo']}»)" if meta else "")
            + ".\n\nNUESTRO PRODUCTO (ficha):\n" + _ficha(textos)
            + ("\n\nLa imagen adjunta es la foto limpia de NUESTRO producto." if foto else
               "\n\n(No hay foto del producto: guíate por la ficha.)")
        )
        start_job(
            job_id=f"replica_viral_{uuid.uuid4().hex[:8]}", program="tiktok_shop_ai_pro",
            mode="replicar_viral", title=f"Replicar viral: {textos.get('titulo', '')[:60]}", user=usuario,
        )
        try:
            crudo = generate_text(
                sistema, mensaje, model=MODELO, expect_json=True, videos=[str(video)],
                images=[str(foto)] if foto else None, temperature=0.6, max_output_tokens=8192,
            )
        finally:
            try:
                finalize_and_persist()
            except Exception:  # noqa: BLE001
                pass
        texto = crudo.strip()
        if texto.startswith("```"):
            texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            resultado = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ErrorReplica(f"La IA no devolvió un JSON válido: {e}", status=502) from e

        guion = ((resultado.get("adaptacion") or {}).get("guion") or "").strip()
        doc = {
            "id": uuid.uuid4().hex[:12],
            "usuario": usuario,
            "creado_at": time.time(),
            "url": url,
            "referencia": meta,
            "producto": {"source": source, "folder": folder, "producto": str(producto),
                         "titulo": textos.get("titulo", ""), "tienda": textos.get("tienda", "")},
            "guion_caracteres": len(guion),
            **resultado,
        }
        r = _redis()
        if r.is_available():
            r.set_json(CLAVE.format(id=doc["id"]), doc)
            indice = r.get_json(INDICE.format(usuario=usuario)) or {"ids": []}
            indice["ids"] = [doc["id"]] + [i for i in indice.get("ids", []) if i != doc["id"]][:199]
            r.set_json(INDICE.format(usuario=usuario), indice)
        return doc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def lista(usuario: str) -> list[dict]:
    r = _redis()
    if not r.is_available():
        return []
    ids = (r.get_json(INDICE.format(usuario=usuario or "ness")) or {}).get("ids") or []
    if not ids:
        return []
    docs = r.mget_json([CLAVE.format(id=i) for i in ids[:50]]) if hasattr(r, "mget_json") else [
        r.get_json(CLAVE.format(id=i)) for i in ids[:50]]
    return [
        {k: d.get(k) for k in ("id", "creado_at", "url", "referencia", "producto", "apto")}
        | {"idea": (d.get("adaptacion") or {}).get("idea", "")}
        for d in docs if isinstance(d, dict)
    ]


def ver(usuario: str, id_: str) -> dict:
    r = _redis()
    d = r.get_json(CLAVE.format(id=id_)) if r.is_available() else None
    if not d or d.get("usuario") != (usuario or "ness"):
        raise ErrorReplica("No existe esa réplica.", status=404)
    return d
