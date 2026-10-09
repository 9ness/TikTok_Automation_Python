"""La música de un carrusel replicado: la del viral (TikTok) y una sin copyright (Meta).

- **TikTok**: la canción que lleva el carrusel original (`music_info` de tikwm):
  título, autor y el enlace al sonido para ponerlo a mano al publicar. Casi
  siempre es un «original sound» de una cuenta de edits — en TikTok vale, fuera
  de TikTok NO (tiene copyright).
- **Meta** (IG/FB/Threads): una pista del banco Mixkit de Multiplataforma
  (`Multiplataforma/_musica/<estilo>/`, licencia libre), con el estilo elegido
  por `multiplataforma.services.musica.elegir_estilo` sobre el título de la
  canción + caption + hashtags. La pista se elige fija por id de la réplica,
  para que todos (operador y agentes) usen la misma.

Defensivo: si algo falla, devuelve lo que tenga y nunca rompe la réplica.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata


def _slug(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-") or "sound"


def de_tikwm(datos: dict) -> dict:
    """La canción del viral a partir del `data` de tikwm ({} si no trae)."""
    m = (datos or {}).get("music_info") or {}
    mid = str(m.get("id") or "").strip()
    if not mid:
        return {}
    titulo = m.get("title") or ""
    return {
        "titulo": titulo,
        "autor": m.get("author") or "",
        "original": bool(m.get("original")),
        "id": mid,
        "enlace": f"https://www.tiktok.com/music/{_slug(titulo)}-{mid}",
    }


def para_meta(id_: str, tiktok: dict, caption: str = "", hashtags: list | None = None) -> dict:
    """Estilo + pista Mixkit fija para publicar el carrusel fuera de TikTok."""
    try:
        from src.multiplataforma import config as mp_config
        from src.multiplataforma.services import musica as mp_musica

        estilo = mp_musica.elegir_estilo({
            "busqueda": "" if (tiktok or {}).get("original") else (tiktok or {}).get("titulo", ""),
            "estilo": " ".join([caption or "", *[h.lstrip("#") for h in (hashtags or [])]]),
        })
        res: dict = {"estilo": estilo}
        indice = mp_config.musica_dir() / "pistas.json"
        lista = (json.loads(indice.read_text(encoding="utf-8")).get(estilo) or []) if indice.is_file() else []
        if lista:
            p = lista[int(hashlib.md5(id_.encode()).hexdigest(), 16) % len(lista)]
            res.update({"pista": p.get("titulo", ""), "autor": p.get("autor", ""),
                        "fichero": f"{mp_config.MUSICA_SUBDIR}/{estilo}/{p.get('fichero', '')}",
                        "url": p.get("url", "")})
        return res
    except Exception:  # noqa: BLE001
        return {}


def completa(doc: dict, datos_tikwm: dict | None = None) -> dict:
    """`doc["musica"]` = {tiktok, meta}. Sin `datos_tikwm` consulta tikwm."""
    tiktok = (doc.get("musica") or {}).get("tiktok") or {}
    if not tiktok:
        try:
            if datos_tikwm is None:
                from src.replicar_viral import servicio

                datos_tikwm = servicio.consultar_tikwm(doc.get("url", ""))
            tiktok = de_tikwm(datos_tikwm or {})
        except Exception:  # noqa: BLE001
            tiktok = {}
    meta = para_meta(doc.get("id", ""), tiktok, doc.get("caption", ""), doc.get("hashtags"))
    return {"tiktok": tiktok, "meta": meta}
