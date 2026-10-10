"""Base común de los clientes: httpx con timeouts, errores claros y modo prueba.

En modo prueba (`dry_run`) ningún método toca la red: se anota cada llamada
que se HARÍA en `self.pasos` y se devuelven ids ficticios, así el publicador
sigue el mismo flujo y el registro dice exactamente qué se enviaría (sin el
token).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from src.multiplataforma import config


class ErrorPublicacion(Exception):
    """Fallo de una plataforma.

    `reintentable` decide si el publicador lo vuelve a probar en el siguiente
    tick; `parcial` guarda lo ya conseguido (p. ej. el id del contenedor de IG)
    para no repetir pasos que crearían un duplicado.
    """

    def __init__(self, mensaje: str, *, reintentable: bool = True, parcial: dict | None = None):
        super().__init__(mensaje)
        self.reintentable = reintentable
        self.parcial = parcial or {}
        # IG: el contenedor acabó en ERROR/EXPIRED y el reintento debe crear otro.
        self.descartar_contenedor = False


def _ocultar(d: dict | None) -> dict:
    return {k: ("***" if "token" in k.lower() else v) for k, v in (d or {}).items()}


class ClienteBase:
    plataforma = "base"

    def __init__(
        self,
        token: str = "",
        *,
        dry_run: bool = False,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_intervalo: float | None = None,
        poll_max: float | None = None,
    ) -> None:
        self.token = token
        self.dry_run = dry_run or not token
        self._http = http
        self._sleep = sleep
        self.poll_intervalo = config.POLL_INTERVALO_S if poll_intervalo is None else poll_intervalo
        self.poll_max = config.POLL_MAX_S if poll_max is None else poll_max
        self.pasos: list[dict] = []

    # ---- http ----
    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=httpx.Timeout(config.HTTP_TIMEOUT_S, connect=15))
        return self._http

    def _anotar(self, metodo: str, url: str, **info: Any) -> None:
        paso = {"metodo": metodo, "url": url}
        for k, v in info.items():
            if v is not None:
                paso[k] = _ocultar(v) if isinstance(v, dict) else v
        self.pasos.append(paso)

    def _request(
        self, metodo: str, url: str, *, params: dict | None = None, data: dict | None = None,
        json: dict | None = None, headers: dict | None = None, content: Any = None,
        files: dict | None = None, timeout: float | None = None, esperar_json: bool = True,
    ) -> Any:
        self._anotar(metodo, url, params=params, data=data, json=json)
        try:
            r = self.http.request(
                metodo, url, params=params, data=data, json=json, headers=headers,
                content=content, files=files,
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.TimeoutException as e:
            raise ErrorPublicacion(f"{self.plataforma}: timeout en {metodo} {url}") from e
        except httpx.HTTPError as e:
            raise ErrorPublicacion(f"{self.plataforma}: error de red en {metodo} {url}: {e}") from e
        if r.status_code >= 400:
            raise ErrorPublicacion(
                f"{self.plataforma}: HTTP {r.status_code} en {metodo} {url}: {self._mensaje_error(r)}",
                reintentable=r.status_code >= 500 or r.status_code == 429,
            )
        if not esperar_json:
            return r
        try:
            return r.json()
        except ValueError:
            return {}

    @staticmethod
    def _mensaje_error(r: httpx.Response) -> str:
        try:
            j = r.json()
        except ValueError:
            return r.text[:300]
        err = j.get("error") if isinstance(j, dict) else None
        if isinstance(err, dict):  # formato Graph API
            return f"{err.get('message', '')} (code={err.get('code')}, subcode={err.get('error_subcode')})"
        if isinstance(j, dict) and j.get("message"):  # formato Pinterest
            return f"{j.get('message')} (code={j.get('code')})"
        return str(j)[:300]

    # ---- utilidades ----
    def _esperar(self, consultar: Callable[[], str], ok: tuple[str, ...], malos: tuple[str, ...],
                 que: str) -> str:
        """Sondea `consultar()` hasta un estado de `ok` (devuelve) o de `malos` (error)."""
        transcurrido = 0.0
        while True:
            estado = (consultar() or "").upper()
            if estado in ok:
                return estado
            if estado in malos:
                raise ErrorPublicacion(f"{self.plataforma}: {que} terminó en {estado}", reintentable=False)
            if transcurrido >= self.poll_max:
                raise ErrorPublicacion(f"{self.plataforma}: {que} sigue en {estado or '?'} tras {int(transcurrido)}s")
            self._sleep(self.poll_intervalo)
            transcurrido += self.poll_intervalo or 1

    @staticmethod
    def _trozos(path: Path, tam: int = 4 * 1024 * 1024) -> Iterator[bytes]:
        with path.open("rb") as f:
            while True:
                b = f.read(tam)
                if not b:
                    return
                yield b

    @staticmethod
    def _fichero(video_path: str) -> Path:
        p = Path(video_path)
        if not p.is_file():
            raise ErrorPublicacion(f"No existe el vídeo {video_path}", reintentable=False)
        return p
