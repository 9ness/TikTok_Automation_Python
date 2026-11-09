"""Codificar los renders del cortador en el PC de casa (GPU) con respaldo local.

El render final del cortador (concat de tramos + codificado H.264) es lo que
más CPU gasta en el VPS. El PC de casa de Néstor tiene una GTX 1050 Ti con
NVENC (8-10x más rápido que libx264) y se alcanza por Tailscale SSH, que no
pide claves. Este módulo:

  1. Comprueba (con caché) que el PC responde y que su ffmpeg abre NVENC.
  2. Sube las entradas por `ssh host 'cat > fichero'` (sin rsync ni scp).
  3. Ejecuta el MISMO comando de ffmpeg allí, con las rutas cambiadas y el
     codificador pasado a NVENC; el progreso llega por la salida de ssh.
  4. Baja el resultado por `ssh host 'cat fichero'` y borra la carpeta remota.

Cualquier fallo (PC apagado, red, ffmpeg, salida vacía) devuelve False y el
llamante renderiza en el VPS como siempre. Apagado por defecto:
`EDITOR_RENDER_REMOTO=1` lo enciende. Nada de claves ni .env viaja al PC:
solo el vídeo del cliente y el comando.

Variables:
  EDITOR_RENDER_REMOTO        1 = intentar en remoto (por defecto 0)
  EDITOR_RENDER_REMOTO_HOST   destino ssh (por defecto ness@100.125.167.31)
  EDITOR_RENDER_REMOTO_DIR    carpeta de trabajo allí (~/worker/remoto)
  EDITOR_RENDER_REMOTO_FFMPEG carpeta del ffmpeg 7 allí (~/worker/ffmpeg7)
  EDITOR_RENDER_REMOTO_SSH    binario ssh (los tests ponen uno falso)
  EDITOR_RENDER_REMOTO_MIN_S  duración mínima para que compense (por defecto 20 s)
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
import uuid
from typing import Callable

_ESTADO: dict = {"ts": 0.0, "ok": False, "nvenc": False}
_CACHE_OK_S = 300.0      # si respondió, no se vuelve a probar en 5 min
_CACHE_KO_S = 120.0      # si no respondió, se reintenta a los 2 min

# Codificador NVENC equivalente al de `silence_cutter._video_encoder_args`.
NVENC_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-rc", "vbr",
              "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"]
_OPCIONES_X264 = {"-preset", "-crf", "-tune", "-pix_fmt", "-threads", "-x264-params"}


def activo() -> bool:
    return os.getenv("EDITOR_RENDER_REMOTO", "0").strip().lower() in ("1", "true", "si", "sí")


def _host() -> str:
    return os.getenv("EDITOR_RENDER_REMOTO_HOST", "ness@100.125.167.31")


def _dir_remoto() -> str:
    return os.getenv("EDITOR_RENDER_REMOTO_DIR", "~/worker/remoto").rstrip("/")


def _ffmpeg_remoto() -> str:
    return os.getenv("EDITOR_RENDER_REMOTO_FFMPEG", "~/worker/ffmpeg7").rstrip("/")


def _min_s() -> float:
    try:
        return float(os.getenv("EDITOR_RENDER_REMOTO_MIN_S", "20"))
    except ValueError:
        return 20.0


def _ssh_base(timeout_conexion: int = 5) -> list[str]:
    known = os.path.join(os.getenv("APP_ROOT", "/app"), "temp_work", ".ssh_known_hosts")
    return [os.getenv("EDITOR_RENDER_REMOTO_SSH", "ssh"),
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={timeout_conexion}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={known}",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4",
            _host()]


def _remoto(comando: str) -> str:
    """Prefijo común: PATH con el ffmpeg 7 del PC (el 6.1 de Ubuntu no vale)."""
    ff = _ffmpeg_remoto()
    return f"export PATH={ff}:\"$PATH\"; {comando}"


def _reset_para_tests() -> None:
    _ESTADO.update(ts=0.0, ok=False, nvenc=False)


def disponible(log: Callable[[str], None] = lambda _: None) -> tuple[bool, bool]:
    """(responde, tiene_nvenc). Con caché para no pagar un ssh por render."""
    edad = time.time() - _ESTADO["ts"]
    if _ESTADO["ts"] and edad < (_CACHE_OK_S if _ESTADO["ok"] else _CACHE_KO_S):
        return _ESTADO["ok"], _ESTADO["nvenc"]
    prueba = ("ffmpeg -hide_banner -loglevel error -f lavfi -i color=c=black:s=64x64:d=0.05:r=10 "
              "-c:v h264_nvenc -frames:v 1 -f null - >/dev/null 2>&1 && echo NVENC || echo CPU")
    ok, nvenc = False, False
    try:
        r = subprocess.run(_ssh_base(4) + [_remoto(prueba)], capture_output=True,
                           text=True, timeout=25)
        salida = (r.stdout or "").strip().splitlines()
        ok = r.returncode == 0 and bool(salida) and salida[-1] in ("NVENC", "CPU")
        nvenc = ok and salida[-1] == "NVENC"
    except Exception as e:  # noqa: BLE001 — cualquier fallo = no disponible
        log(f"[render_remoto] PC de casa no responde: {e}")
    _ESTADO.update(ts=time.time(), ok=ok, nvenc=nvenc)
    return ok, nvenc


def preparar(cmd: list[str], dir_remoto: str) -> tuple[list[str], dict[str, str], str] | None:
    """Reescribe un comando ffmpeg para el PC.

    Devuelve (cmd_remoto, {local: remoto} de entradas, salida_local) o None si
    el comando no es seguro de mover: no es ffmpeg, la salida no es un .mp4,
    o algún argumento que no sea `-i` apunta a un fichero local (subtítulos,
    fuentes, `movie=`…), que allí no existiría.
    """
    if not cmd or os.path.basename(cmd[0]) != "ffmpeg" or len(cmd) < 4:
        return None
    salida = cmd[-1]
    if not salida.lower().endswith(".mp4") or salida.startswith("-"):
        return None
    entradas: dict[str, str] = {}
    nuevo = [cmd[0]]
    i = 1
    while i < len(cmd) - 1:
        a = cmd[i]
        if a == "-i" and i + 1 < len(cmd) - 1:
            src = cmd[i + 1]
            if not os.path.isfile(src):
                return None
            if src not in entradas:
                ext = os.path.splitext(src)[1] or ".bin"
                entradas[src] = f"{dir_remoto}/in{len(entradas)}{ext}"
            nuevo += ["-i", entradas[src]]
            i += 2
            continue
        # Un fichero local en otro sitio (filtro con ruta, fuente…) → no se mueve.
        if os.path.isabs(a) and os.path.exists(a):
            return None
        if "/" in a and any(t in a for t in ("subtitles=", "ass=", "movie=", "fontfile=", "amovie=")):
            return None
        nuevo.append(a)
        i += 1
    if not entradas:
        return None
    nuevo.append(f"{dir_remoto}/out.mp4")
    return nuevo, entradas, salida


def cambiar_a_nvenc(cmd: list[str]) -> list[str]:
    """Sustituye `-c:v libx264` y sus opciones por los args NVENC."""
    if "libx264" not in cmd:
        return cmd
    out: list[str] = []
    i = 0
    puesto = False
    while i < len(cmd):
        a = cmd[i]
        if a == "-c:v" and i + 1 < len(cmd) and cmd[i + 1] == "libx264":
            if not puesto:
                out += NVENC_ARGS
                puesto = True
            i += 2
            continue
        if puesto and a in _OPCIONES_X264 and i + 1 < len(cmd):
            i += 2  # opción propia de libx264 (o pix_fmt, ya incluido)
            continue
        out.append(a)
        i += 1
    return out


def _subir(local: str, remoto: str, timeout: float) -> None:
    with open(local, "rb") as f:
        r = subprocess.run(_ssh_base() + [f"cat > {remoto}"], stdin=f,
                           capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"subida falló ({r.returncode}): {r.stderr[-300:]!r}")


def _bajar(remoto: str, local: str, timeout: float) -> None:
    tmp = local + ".remoto.part"
    try:
        with open(tmp, "wb") as f:
            r = subprocess.run(_ssh_base() + [f"cat {remoto}"], stdout=f,
                               stderr=subprocess.PIPE, timeout=timeout)
        if r.returncode != 0 or os.path.getsize(tmp) < 1024:
            raise RuntimeError(f"bajada falló ({r.returncode}): {r.stderr[-300:]!r}")
        os.replace(tmp, local)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _quote_remoto(ruta: str) -> str:
    """Comillas para el shell remoto dejando que `~/` se expanda."""
    if ruta.startswith("~/"):
        return "~/" + shlex.quote(ruta[2:])
    return shlex.quote(ruta)


def intentar(cmd: list[str], *, ejecutar: Callable[[list[str]], None],
             duracion_s: float | None = None,
             log: Callable[[str], None] = lambda _: None) -> bool:
    """Intenta el render en el PC de casa. True = hecho y salida en su sitio.

    `ejecutar(cmd_ssh)` es el ejecutor con progreso del cortador: se le pasa
    el comando ssh y él añade `-progress pipe:1`, que viaja por ssh igual.
    """
    if not activo():
        return False
    if duracion_s is not None and duracion_s < _min_s():
        return False  # en vídeos cortos no compensa subir y bajar
    trabajo = f"{_dir_remoto()}/{uuid.uuid4().hex[:12]}"
    prep = preparar(cmd, trabajo)
    if prep is None:
        return False
    ok, nvenc = disponible(log)
    if not ok:
        return False
    cmd_remoto, entradas, salida = prep
    if nvenc:
        cmd_remoto = cambiar_a_nvenc(cmd_remoto)
    tam = sum(os.path.getsize(p) for p in entradas)
    t_red = max(60.0, tam / (2 * 1024 * 1024))  # ≥2 MB/s o se da por caído
    t0 = time.time()
    dq = _quote_remoto(trabajo)
    try:
        r = subprocess.run(_ssh_base() + [f"mkdir -p {dq}"], capture_output=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError("mkdir remoto falló")
        for local, remoto in entradas.items():
            _subir(local, _quote_remoto(remoto), t_red)
        t_sub = time.time() - t0
        linea = " ".join(_quote_remoto(a) if a.startswith("~/") else shlex.quote(a)
                         for a in cmd_remoto)
        ejecutar(_ssh_base() + [_remoto(linea)])
        t_enc = time.time() - t0 - t_sub
        _bajar(_quote_remoto(f"{trabajo}/out.mp4"), salida, t_red)
        log(f"[render_remoto] PC de casa ({'NVENC' if nvenc else 'CPU'}) · "
            f"subida {t_sub:.1f}s · render {t_enc:.1f}s · total {time.time() - t0:.1f}s")
        return True
    except Exception as e:  # noqa: BLE001 — respaldo local siempre
        log(f"[render_remoto] falló en el PC de casa, se hace en el VPS: {str(e)[:300]}")
        _ESTADO.update(ts=time.time(), ok=False)  # no reintentar enseguida
        return False
    finally:
        try:
            subprocess.run(_ssh_base(3) + [f"rm -rf {dq}"], capture_output=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass
