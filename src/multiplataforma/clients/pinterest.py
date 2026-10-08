"""Pinterest API v5: pin de vídeo.

Flujo:
1. `POST /v5/media` {"media_type": "video"} → media_id, upload_url y
   upload_parameters (formulario de S3).
2. Subida multipart a `upload_url` con esos campos + el fichero.
3. Sondeo de `GET /v5/media/{media_id}` hasta status=succeeded.
4. `POST /v5/pins` con board_id, title, description, link y
   media_source {source_type: "video_id", media_id, cover_image_url}
   (o cover_image_key_frame_time si no hay portada).

Ojo: con acceso «Trial» Pinterest solo deja crear pines en el sandbox
(`PINTEREST_API_BASE=https://api-sandbox.pinterest.com/v5`).
"""

from __future__ import annotations

from src.multiplataforma import config
from src.multiplataforma.clients.base import ClienteBase, ErrorPublicacion


class PinterestClient(ClienteBase):
    plataforma = "pinterest"

    def __init__(self, token: str = "", **kw) -> None:
        super().__init__(token, **kw)
        self.base = config.pinterest_base()

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def publicar(self, board_id: str, *, titulo: str, descripcion: str, enlace: str, video_path: str,
                 cover_url: str = "", previo: dict | None = None) -> dict:
        previo = previo or {}
        if not board_id:
            raise ErrorPublicacion("pinterest: la cuenta no tiene pinterest_board_id", reintentable=False)
        media_id = previo.get("media_id", "")
        if not media_id:
            media_id = self._registrar_y_subir(video_path)
        try:
            self._esperar_media(media_id)
            pin_id = self._crear_pin(board_id, media_id, titulo=titulo, descripcion=descripcion,
                                     enlace=enlace, cover_url=cover_url)
        except ErrorPublicacion as e:
            e.parcial = {**e.parcial, "media_id": media_id}
            raise
        return {"media_id": media_id, "pin_id": pin_id, "dry_run": self.dry_run, "pasos": self.pasos}

    def _registrar_y_subir(self, video_path: str) -> str:
        url = f"{self.base}/media"
        if self.dry_run:
            self._anotar("POST", url, json={"media_type": "video"})
            self._anotar("POST", "<upload_url de S3>", nota=f"multipart {video_path}")
            return "dry-pin-media"
        p = self._fichero(video_path)
        j = self._request("POST", url, json={"media_type": "video"}, headers=self._auth())
        media_id = str(j.get("media_id") or "")
        upload_url = j.get("upload_url") or ""
        if not media_id or not upload_url:
            raise ErrorPublicacion(f"pinterest: /media sin media_id/upload_url: {j}")
        campos = {k: str(v) for k, v in (j.get("upload_parameters") or {}).items()}
        with p.open("rb") as f:
            # S3 responde 204 sin cuerpo
            self._request("POST", upload_url, data=campos, files={"file": (p.name, f, "video/mp4")},
                          timeout=config.UPLOAD_TIMEOUT_S, esperar_json=False)
        return media_id

    def _esperar_media(self, media_id: str) -> None:
        url = f"{self.base}/media/{media_id}"
        if self.dry_run:
            self._anotar("GET", url, nota="sondeo hasta succeeded")
            return

        def consultar() -> str:
            return self._request("GET", url, headers=self._auth()).get("status") or ""

        self._esperar(consultar, ok=("SUCCEEDED",), malos=("FAILED",), que=f"media {media_id}")

    def _crear_pin(self, board_id: str, media_id: str, *, titulo: str, descripcion: str, enlace: str,
                   cover_url: str) -> str:
        fuente: dict = {"source_type": "video_id", "media_id": media_id}
        if cover_url:
            fuente["cover_image_url"] = cover_url
        else:
            fuente["cover_image_key_frame_time"] = 1
        cuerpo = {
            "board_id": board_id,
            "title": titulo[: config.MAX_TITULO_PINTEREST],
            "description": descripcion[: config.MAX_CHARS["pinterest"]],
            "media_source": fuente,
        }
        if enlace:
            cuerpo["link"] = enlace
        url = f"{self.base}/pins"
        if self.dry_run:
            self._anotar("POST", url, json=cuerpo)
            return "dry-pin"
        j = self._request("POST", url, json=cuerpo, headers=self._auth())
        pin_id = str(j.get("id") or "")
        if not pin_id:
            raise ErrorPublicacion(f"pinterest: /pins sin id: {j}")
        return pin_id
