"""Instagram Reels por la Graph API (Content Publishing).

Flujo:
1. (opcional) `GET /{ig}/content_publishing_limit` — cuota real de la cuenta.
2. `POST /{ig}/media` media_type=REELS con `video_url` público, o con
   `upload_type=resumable` + subida del binario a rupload.facebook.com.
   Para `prueba_viral` se añade `trial_params` (reel de prueba: solo lo ven no
   seguidores; graduation_strategy MANUAL o SS_PERFORMANCE).
3. Sondeo de `status_code` del contenedor hasta FINISHED.
4. `POST /{ig}/media_publish` creation_id=<contenedor>.

Si un intento falla después de crear el contenedor, el id viaja en
`ErrorPublicacion.parcial` y el reintento lo reutiliza (no se crea otro).
"""

from __future__ import annotations

import json

from src.multiplataforma import config
from src.multiplataforma.clients.base import ClienteBase, ErrorPublicacion

GRADUACIONES = ("MANUAL", "SS_PERFORMANCE")


class InstagramClient(ClienteBase):
    plataforma = "instagram"

    def __init__(self, token: str = "", **kw) -> None:
        super().__init__(token, **kw)
        self.base = config.graph_base()

    def cuota(self, ig_user_id: str) -> dict:
        """{'usado': n, 'total': m} según Meta (en prueba, sin consultar)."""
        url = f"{self.base}/{ig_user_id}/content_publishing_limit"
        if self.dry_run:
            self._anotar("GET", url)
            return {"usado": 0, "total": config.LIMITES_24H["instagram"]}
        j = self._request("GET", url, params={"fields": "config,quota_usage", "access_token": self.token})
        fila = (j.get("data") or [{}])[0]
        return {
            "usado": int(fila.get("quota_usage") or 0),
            "total": int((fila.get("config") or {}).get("quota_total") or config.LIMITES_24H["instagram"]),
        }

    def publicar(
        self, ig_user_id: str, *, caption: str, video_url: str = "", video_path: str = "",
        cover_url: str = "", trial: bool = False, graduacion: str = "MANUAL",
        previo: dict | None = None,
    ) -> dict:
        previo = previo or {}
        if not ig_user_id:
            raise ErrorPublicacion("instagram: la cuenta no tiene ig_user_id", reintentable=False)
        if not video_url and not video_path:
            raise ErrorPublicacion("instagram: hace falta video_url o video_path", reintentable=False)

        cuota = self.cuota(ig_user_id)
        if cuota["usado"] >= cuota["total"]:
            raise ErrorPublicacion(f"instagram: cuota de Meta agotada ({cuota['usado']}/{cuota['total']})")

        contenedor = previo.get("container_id", "")
        if not contenedor:
            contenedor = self._crear_contenedor(
                ig_user_id, caption=caption, video_url=video_url, video_path=video_path,
                cover_url=cover_url, trial=trial, graduacion=graduacion,
            )
        try:
            self._esperar_contenedor(contenedor)
            media_id = self._publicar_contenedor(ig_user_id, contenedor)
        except ErrorPublicacion as e:
            e.parcial = {**e.parcial, "container_id": contenedor}
            raise
        return {
            "container_id": contenedor,
            "media_id": media_id,
            "trial": trial,
            "dry_run": self.dry_run,
            "pasos": self.pasos,
        }

    def _crear_contenedor(self, ig_user_id: str, *, caption: str, video_url: str, video_path: str,
                          cover_url: str, trial: bool, graduacion: str) -> str:
        url = f"{self.base}/{ig_user_id}/media"
        datos: dict = {"media_type": "REELS", "caption": caption, "share_to_feed": "true"}
        if cover_url:
            datos["cover_url"] = cover_url
        if trial:
            g = (graduacion or "MANUAL").upper()
            if g not in GRADUACIONES:
                raise ErrorPublicacion(f"instagram: graduation_strategy no válida: {g}", reintentable=False)
            datos["trial_params"] = json.dumps({"graduation_strategy": g})
        resumable = not video_url
        if resumable:
            datos["upload_type"] = "resumable"
        else:
            datos["video_url"] = video_url

        if self.dry_run:
            self._anotar("POST", url, data=datos)
            contenedor = "dry-ig-container"
        else:
            j = self._request("POST", url, data={**datos, "access_token": self.token})
            contenedor = str(j.get("id") or "")
            if not contenedor:
                raise ErrorPublicacion(f"instagram: Meta no devolvió id de contenedor: {j}")
            if resumable:
                self._subir_resumable(contenedor, video_path, j.get("uri") or "")
        if self.dry_run and resumable:
            self._anotar("POST", f"{config.rupload_base()}/ig-api-upload/{config.graph_version()}/{contenedor}",
                         nota=f"binario {video_path}")
        return contenedor

    def _subir_resumable(self, contenedor: str, video_path: str, uri: str) -> None:
        p = self._fichero(video_path)
        url = uri or f"{config.rupload_base()}/ig-api-upload/{config.graph_version()}/{contenedor}"
        try:
            self._request(
                "POST", url,
                headers={"Authorization": f"OAuth {self.token}", "offset": "0",
                         "file_size": str(p.stat().st_size)},
                # entero, no por trozos: con chunked rupload da 400 (pide Content-Length)
                content=p.read_bytes(), timeout=config.UPLOAD_TIMEOUT_S,
            )
        except ErrorPublicacion as e:
            # el contenedor sin vídeo no sirve: que el reintento cree otro
            e.parcial = {}
            raise

    def _esperar_contenedor(self, contenedor: str) -> None:
        url = f"{self.base}/{contenedor}"
        if self.dry_run:
            self._anotar("GET", url, params={"fields": "status_code,status"}, nota="sondeo hasta FINISHED")
            return

        def consultar() -> str:
            j = self._request("GET", url, params={"fields": "status_code,status", "access_token": self.token})
            return j.get("status_code") or ""

        self._esperar(consultar, ok=("FINISHED", "PUBLISHED"), malos=("ERROR", "EXPIRED"),
                      que=f"contenedor {contenedor}")

    def _publicar_contenedor(self, ig_user_id: str, contenedor: str) -> str:
        url = f"{self.base}/{ig_user_id}/media_publish"
        if self.dry_run:
            self._anotar("POST", url, data={"creation_id": contenedor})
            return "dry-ig-media"
        j = self._request("POST", url, data={"creation_id": contenedor, "access_token": self.token})
        media_id = str(j.get("id") or "")
        if not media_id:
            raise ErrorPublicacion(f"instagram: media_publish sin id: {j}")
        return media_id

    # ---- carrusel de fotos ----
    def publicar_carrusel(self, ig_user_id: str, *, caption: str, imagenes_url: list[str],
                          previo: dict | None = None) -> dict:
        """Carrusel de 2-10 fotos: un contenedor IMAGE `is_carousel_item` por
        foto → contenedor CAROUSEL con `children` → `media_publish`. Las fotos
        tienen que ser JPEG entre 4:5 y 1.91:1 (Meta rechaza 3:4 y 9:16: van
        ya adaptadas a 4:5, ver `services/carruseles.py`)."""
        previo = previo or {}
        if not ig_user_id:
            raise ErrorPublicacion("instagram: la cuenta no tiene ig_user_id", reintentable=False)
        if not 2 <= len(imagenes_url) <= config.MAX_FOTOS_CARRUSEL["instagram"]:
            raise ErrorPublicacion(f"instagram: un carrusel lleva de 2 a 10 fotos ({len(imagenes_url)})",
                                   reintentable=False)
        cuota = self.cuota(ig_user_id)
        if cuota["usado"] >= cuota["total"]:
            raise ErrorPublicacion(f"instagram: cuota de Meta agotada ({cuota['usado']}/{cuota['total']})")

        hijos: list[str] = list(previo.get("children") or [])
        contenedor = previo.get("container_id", "")
        try:
            if not contenedor:
                url = f"{self.base}/{ig_user_id}/media"
                for i, img in enumerate(imagenes_url[len(hijos):], start=len(hijos)):
                    datos = {"image_url": img, "is_carousel_item": "true"}
                    if self.dry_run:
                        self._anotar("POST", url, data=datos)
                        hijos.append(f"dry-ig-item-{i + 1}")
                        continue
                    j = self._request("POST", url, data={**datos, "access_token": self.token})
                    if not j.get("id"):
                        raise ErrorPublicacion(f"instagram: foto {i + 1} sin id de contenedor: {j}")
                    hijos.append(str(j["id"]))
                for h in hijos:
                    self._esperar_contenedor(h)
                datos = {"media_type": "CAROUSEL", "children": ",".join(hijos), "caption": caption}
                if self.dry_run:
                    self._anotar("POST", url, data=datos)
                    contenedor = "dry-ig-carousel"
                else:
                    j = self._request("POST", url, data={**datos, "access_token": self.token})
                    contenedor = str(j.get("id") or "")
                    if not contenedor:
                        raise ErrorPublicacion(f"instagram: Meta no devolvió id del carrusel: {j}")
            self._esperar_contenedor(contenedor)
            media_id = self._publicar_contenedor(ig_user_id, contenedor)
        except ErrorPublicacion as e:
            e.parcial = {**e.parcial, "children": hijos, **({"container_id": contenedor} if contenedor else {})}
            raise
        return {"children": hijos, "container_id": contenedor, "media_id": media_id,
                "dry_run": self.dry_run, "pasos": self.pasos}
