"""Facebook Page Reels por la Graph API.

Flujo:
1. `POST /{page_id}/video_reels` upload_phase=start → video_id (+ upload_url).
2. Binario a `rupload.facebook.com/video-upload/{ver}/{video_id}` (cabeceras
   offset/file_size, Authorization: OAuth <token de página>).
3. `POST /{page_id}/video_reels` upload_phase=finish video_state=PUBLISHED
   description=<texto>.
4. Espera a que el reel esté publicado y deja el enlace en el primer
   comentario (`POST /{video_id}/comments`): en la descripción de un reel el
   enlace no es clicable.

El comentario es aparte: si falla, el reel YA está publicado (no se repite) y
el fallo queda en `comentario_error` para reintentarlo a mano.
"""

from __future__ import annotations

from src.multiplataforma import config
from src.multiplataforma.clients.base import ClienteBase, ErrorPublicacion


class FacebookClient(ClienteBase):
    plataforma = "facebook"

    def __init__(self, token: str = "", **kw) -> None:
        super().__init__(token, **kw)
        self.base = config.graph_base()

    def publicar(self, page_id: str, *, descripcion: str, video_path: str, comentario: str = "",
                 previo: dict | None = None) -> dict:
        previo = previo or {}
        if not page_id:
            raise ErrorPublicacion("facebook: la cuenta no tiene fb_page_id", reintentable=False)
        url = f"{self.base}/{page_id}/video_reels"

        video_id = previo.get("video_id", "")
        if not video_id:
            video_id, upload_url = self._start(url)
            self._subir(video_id, upload_url, video_path)
        try:
            self._finish(url, video_id, descripcion)
            self._esperar_publicado(video_id)
        except ErrorPublicacion as e:
            e.parcial = {**e.parcial, "video_id": video_id}
            raise

        res = {"video_id": video_id, "dry_run": self.dry_run, "pasos": self.pasos}
        if comentario:
            try:
                res["comentario_id"] = self.comentar(video_id, comentario)
            except ErrorPublicacion as e:
                res["comentario_error"] = str(e)
        return res

    def _start(self, url: str) -> tuple[str, str]:
        if self.dry_run:
            self._anotar("POST", url, data={"upload_phase": "start"})
            return "dry-fb-video", ""
        j = self._request("POST", url, data={"upload_phase": "start", "access_token": self.token})
        video_id = str(j.get("video_id") or "")
        if not video_id:
            raise ErrorPublicacion(f"facebook: start sin video_id: {j}")
        return video_id, j.get("upload_url") or ""

    def _subir(self, video_id: str, upload_url: str, video_path: str) -> None:
        url = upload_url or f"{config.rupload_base()}/video-upload/{config.graph_version()}/{video_id}"
        if self.dry_run:
            self._anotar("POST", url, nota=f"binario {video_path}")
            return
        p = self._fichero(video_path)
        self._request(
            "POST", url,
            headers={"Authorization": f"OAuth {self.token}", "offset": "0",
                     "file_size": str(p.stat().st_size)},
            content=self._trozos(p), timeout=config.UPLOAD_TIMEOUT_S,
        )

    def _finish(self, url: str, video_id: str, descripcion: str) -> None:
        datos = {"upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
                 "description": descripcion}
        if self.dry_run:
            self._anotar("POST", url, data=datos)
            return
        j = self._request("POST", url, data={**datos, "access_token": self.token})
        if j.get("success") is False:
            raise ErrorPublicacion(f"facebook: finish rechazado: {j}")

    def _esperar_publicado(self, video_id: str) -> None:
        url = f"{self.base}/{video_id}"
        if self.dry_run:
            self._anotar("GET", url, params={"fields": "status"}, nota="sondeo hasta publicado")
            return

        def consultar() -> str:
            j = self._request("GET", url, params={"fields": "status", "access_token": self.token})
            st = j.get("status") or {}
            if (st.get("video_status") or "").lower() == "error":
                return "ERROR"
            fase = (st.get("publishing_phase") or {}).get("status", "")
            return "PUBLICADO" if fase == "complete" else (st.get("video_status") or "").upper()

        self._esperar(consultar, ok=("PUBLICADO",), malos=("ERROR",), que=f"reel {video_id}")

    def comentar(self, objeto_id: str, mensaje: str) -> str:
        url = f"{self.base}/{objeto_id}/comments"
        if self.dry_run:
            self._anotar("POST", url, data={"message": mensaje})
            return "dry-fb-comment"
        j = self._request("POST", url, data={"message": mensaje, "access_token": self.token})
        return str(j.get("id") or "")
