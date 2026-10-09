"""Threads por la Threads API (graph.threads.net).

Flujo: `POST /{uid}/threads` media_type=VIDEO video_url text → sondeo de
`status` hasta FINISHED → `POST /{uid}/threads_publish` creation_id. El enlace
va dentro del texto (en Threads sí es clicable). Antes se mira la cuota real
(`/threads_publishing_limit`).
"""

from __future__ import annotations

from src.multiplataforma import config
from src.multiplataforma.clients.base import ClienteBase, ErrorPublicacion


class ThreadsClient(ClienteBase):
    plataforma = "threads"

    def __init__(self, token: str = "", **kw) -> None:
        super().__init__(token, **kw)
        self.base = config.threads_base()

    def cuota(self, user_id: str) -> dict:
        url = f"{self.base}/{user_id}/threads_publishing_limit"
        if self.dry_run:
            self._anotar("GET", url)
            return {"usado": 0, "total": config.LIMITES_24H["threads"]}
        j = self._request("GET", url, params={"fields": "quota_usage,config", "access_token": self.token})
        fila = (j.get("data") or [{}])[0]
        return {
            "usado": int(fila.get("quota_usage") or 0),
            "total": int((fila.get("config") or {}).get("quota_total") or config.LIMITES_24H["threads"]),
        }

    def publicar(self, user_id: str, *, texto: str, video_url: str, previo: dict | None = None) -> dict:
        previo = previo or {}
        if not user_id:
            raise ErrorPublicacion("threads: la cuenta no tiene threads_user_id", reintentable=False)
        if not video_url:
            raise ErrorPublicacion("threads: hace falta video_url público", reintentable=False)
        if len(texto) > config.MAX_CHARS["threads"]:
            raise ErrorPublicacion("threads: el texto pasa de 500 caracteres", reintentable=False)

        cuota = self.cuota(user_id)
        if cuota["usado"] >= cuota["total"]:
            raise ErrorPublicacion(f"threads: cuota agotada ({cuota['usado']}/{cuota['total']})")

        contenedor = previo.get("container_id", "")
        if not contenedor:
            contenedor = self._crear(user_id, texto, video_url)
        try:
            self._esperar_contenedor(contenedor)
            post_id = self._publicar(user_id, contenedor)
        except ErrorPublicacion as e:
            e.parcial = {**e.parcial, "container_id": contenedor}
            raise
        return {"container_id": contenedor, "post_id": post_id, "dry_run": self.dry_run, "pasos": self.pasos}

    def _crear(self, user_id: str, texto: str, video_url: str) -> str:
        url = f"{self.base}/{user_id}/threads"
        datos = {"media_type": "VIDEO", "video_url": video_url, "text": texto}
        if self.dry_run:
            self._anotar("POST", url, data=datos)
            return "dry-th-container"
        j = self._request("POST", url, data={**datos, "access_token": self.token})
        cid = str(j.get("id") or "")
        if not cid:
            raise ErrorPublicacion(f"threads: sin id de contenedor: {j}")
        return cid

    def _esperar_contenedor(self, contenedor: str) -> None:
        url = f"{self.base}/{contenedor}"
        if self.dry_run:
            self._anotar("GET", url, params={"fields": "status,error_message"}, nota="sondeo hasta FINISHED")
            return

        def consultar() -> str:
            j = self._request("GET", url, params={"fields": "status,error_message", "access_token": self.token})
            return j.get("status") or ""

        self._esperar(consultar, ok=("FINISHED", "PUBLISHED"), malos=("ERROR", "EXPIRED"),
                      que=f"contenedor {contenedor}")

    def _publicar(self, user_id: str, contenedor: str) -> str:
        url = f"{self.base}/{user_id}/threads_publish"
        if self.dry_run:
            self._anotar("POST", url, data={"creation_id": contenedor})
            return "dry-th-post"
        j = self._request("POST", url, data={"creation_id": contenedor, "access_token": self.token})
        pid = str(j.get("id") or "")
        if not pid:
            raise ErrorPublicacion(f"threads: threads_publish sin id: {j}")
        return pid

    # ---- carrusel de fotos ----
    def publicar_carrusel(self, user_id: str, *, texto: str, imagenes_url: list[str],
                          previo: dict | None = None) -> dict:
        """Items IMAGE `is_carousel_item` → contenedor CAROUSEL (children +
        text) → `threads_publish`. De 2 a 20 fotos."""
        previo = previo or {}
        if not user_id:
            raise ErrorPublicacion("threads: la cuenta no tiene threads_user_id", reintentable=False)
        if not 2 <= len(imagenes_url) <= config.MAX_FOTOS_CARRUSEL["threads"]:
            raise ErrorPublicacion(f"threads: un carrusel lleva de 2 a 20 fotos ({len(imagenes_url)})",
                                   reintentable=False)
        if len(texto) > config.MAX_CHARS["threads"]:
            raise ErrorPublicacion("threads: el texto pasa de 500 caracteres", reintentable=False)
        cuota = self.cuota(user_id)
        if cuota["usado"] >= cuota["total"]:
            raise ErrorPublicacion(f"threads: cuota agotada ({cuota['usado']}/{cuota['total']})")

        hijos: list[str] = list(previo.get("children") or [])
        contenedor = previo.get("container_id", "")
        url = f"{self.base}/{user_id}/threads"
        try:
            if not contenedor:
                for i, img in enumerate(imagenes_url[len(hijos):], start=len(hijos)):
                    datos = {"media_type": "IMAGE", "image_url": img, "is_carousel_item": "true"}
                    if self.dry_run:
                        self._anotar("POST", url, data=datos)
                        hijos.append(f"dry-th-item-{i + 1}")
                        continue
                    j = self._request("POST", url, data={**datos, "access_token": self.token})
                    if not j.get("id"):
                        raise ErrorPublicacion(f"threads: foto {i + 1} sin id de contenedor: {j}")
                    hijos.append(str(j["id"]))
                for h in hijos:
                    self._esperar_contenedor(h)
                datos = {"media_type": "CAROUSEL", "children": ",".join(hijos), "text": texto}
                if self.dry_run:
                    self._anotar("POST", url, data=datos)
                    contenedor = "dry-th-carousel"
                else:
                    j = self._request("POST", url, data={**datos, "access_token": self.token})
                    contenedor = str(j.get("id") or "")
                    if not contenedor:
                        raise ErrorPublicacion(f"threads: sin id del carrusel: {j}")
            self._esperar_contenedor(contenedor)
            post_id = self._publicar(user_id, contenedor)
        except ErrorPublicacion as e:
            e.parcial = {**e.parcial, "children": hijos, **({"container_id": contenedor} if contenedor else {})}
            raise
        return {"children": hijos, "container_id": contenedor, "post_id": post_id,
                "dry_run": self.dry_run, "pasos": self.pasos}
