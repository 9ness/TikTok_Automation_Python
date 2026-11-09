"""Registro de conversaciones y estado de cada chat, en un SQLite local.

El bot vive en vps-webs, que no tiene el Redis de la fábrica: un fichero
SQLite basta (un negocio, pocos mensajes) y no añade ninguna dependencia.

Tablas:
- ``mensajes``: todo lo que entra y sale (registro de conversaciones). El
  ``wamid`` es único, así que un webhook repetido por Meta no se procesa dos
  veces.
- ``chats``: estado por cliente — último mensaje suyo (ventana de 24 h),
  pausa del bot y hasta cuándo, avisos ya dados.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

VENTANA_SERVICIO_S = 24 * 3600

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_id TEXT NOT NULL,
    direccion TEXT NOT NULL,      -- entra | sale | eco
    origen TEXT NOT NULL,         -- cliente | bot | ia | nestor | plantilla
    tipo TEXT NOT NULL DEFAULT 'text',
    texto TEXT NOT NULL DEFAULT '',
    wamid TEXT UNIQUE,
    estado TEXT NOT NULL DEFAULT '',
    ts INTEGER NOT NULL,
    extra TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS mensajes_chat ON mensajes (wa_id, ts);
CREATE TABLE IF NOT EXISTS chats (
    wa_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL DEFAULT '',
    ultimo_entrante INTEGER NOT NULL DEFAULT 0,
    pausado_hasta INTEGER NOT NULL DEFAULT 0,
    motivo_pausa TEXT NOT NULL DEFAULT '',
    aviso_fuera_horario INTEGER NOT NULL DEFAULT 0,
    ia_dia TEXT NOT NULL DEFAULT '',
    ia_usos INTEGER NOT NULL DEFAULT 0,
    esperando TEXT NOT NULL DEFAULT '',   -- '' | email | codigo (vinculación en curso)
    dato_espera TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS datos (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ia_llamadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    wa_id TEXT NOT NULL,
    modelo TEXT NOT NULL,
    entrada INTEGER NOT NULL DEFAULT 0,
    salida INTEGER NOT NULL DEFAULT 0,
    usd REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alias (
    user_id TEXT PRIMARY KEY,     -- BSUID de Meta
    wa_id TEXT NOT NULL           -- teléfono con el que ya conocíamos ese chat
);
"""


class Almacen:
    """Acceso al SQLite. Una conexión con candado: el tráfico es mínimo."""

    def __init__(self, ruta: str | Path = ":memory:") -> None:
        if str(ruta) != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(ruta), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._candado = threading.Lock()
        with self._candado:
            self._db.executescript(_ESQUEMA)
            self._db.commit()

    # ── identidad ───────────────────────────────────────────────────────────
    def clave_chat(self, wa_id: str, user_id: str = "") -> str:
        """Clave única del chat aunque Meta mande unas veces teléfono y otras BSUID.

        Si llegan los dos se recuerda la pareja; si luego llega solo el BSUID
        (p. ej. en el eco de lo que escribe Néstor) se devuelve el teléfono.
        """
        if not user_id:
            return wa_id
        with self._candado:
            if wa_id and wa_id != user_id:
                self._db.execute(
                    "INSERT OR REPLACE INTO alias (user_id, wa_id) VALUES (?, ?)", (user_id, wa_id)
                )
                self._db.commit()
                return wa_id
            fila = self._db.execute("SELECT wa_id FROM alias WHERE user_id = ?", (user_id,)).fetchone()
        return str(fila["wa_id"]) if fila else user_id

    # ── mensajes ────────────────────────────────────────────────────────────
    def registrar(
        self,
        wa_id: str,
        direccion: str,
        origen: str,
        texto: str = "",
        *,
        tipo: str = "text",
        wamid: str | None = None,
        ts: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Guarda un mensaje. Devuelve False si ese ``wamid`` ya estaba."""
        with self._candado:
            try:
                self._db.execute(
                    "INSERT INTO mensajes (wa_id, direccion, origen, tipo, texto, wamid, ts, extra)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        wa_id,
                        direccion,
                        origen,
                        tipo,
                        texto,
                        wamid or None,
                        int(ts or time.time()),
                        json.dumps(extra or {}, ensure_ascii=False),
                    ),
                )
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def marcar_estado(self, wamid: str, estado: str) -> None:
        with self._candado:
            self._db.execute("UPDATE mensajes SET estado = ? WHERE wamid = ?", (estado, wamid))
            self._db.commit()

    def es_nuestro(self, wamid: str) -> bool:
        """True si ese mensaje lo mandó el bot por la API (no Néstor a mano)."""
        with self._candado:
            fila = self._db.execute(
                "SELECT 1 FROM mensajes WHERE wamid = ? AND direccion = 'sale'", (wamid,)
            ).fetchone()
        return fila is not None

    def historial(self, wa_id: str, limite: int = 12) -> list[dict[str, Any]]:
        """Últimos mensajes del chat, del más antiguo al más nuevo."""
        with self._candado:
            filas = self._db.execute(
                "SELECT direccion, origen, tipo, texto, ts FROM mensajes"
                " WHERE wa_id = ? ORDER BY id DESC LIMIT ?",
                (wa_id, limite),
            ).fetchall()
        return [dict(f) for f in reversed(filas)]

    def conversaciones(self, limite: int = 50) -> list[dict[str, Any]]:
        """Resumen por chat para la página del panel."""
        with self._candado:
            filas = self._db.execute(
                "SELECT c.wa_id, c.nombre, c.ultimo_entrante, c.pausado_hasta, c.motivo_pausa,"
                " (SELECT COUNT(*) FROM mensajes m WHERE m.wa_id = c.wa_id) AS mensajes,"
                " (SELECT texto FROM mensajes m WHERE m.wa_id = c.wa_id ORDER BY id DESC LIMIT 1)"
                "   AS ultimo_texto"
                " FROM chats c ORDER BY c.ultimo_entrante DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [dict(f) for f in filas]

    # ── estado del chat ─────────────────────────────────────────────────────
    def _asegurar(self, wa_id: str) -> None:
        self._db.execute("INSERT OR IGNORE INTO chats (wa_id) VALUES (?)", (wa_id,))

    def chat(self, wa_id: str) -> dict[str, Any]:
        with self._candado:
            self._asegurar(wa_id)
            self._db.commit()
            fila = self._db.execute("SELECT * FROM chats WHERE wa_id = ?", (wa_id,)).fetchone()
        return dict(fila)

    def anotar_entrante(self, wa_id: str, nombre: str = "", ts: int | None = None) -> None:
        with self._candado:
            self._asegurar(wa_id)
            self._db.execute(
                "UPDATE chats SET ultimo_entrante = ?,"
                " nombre = CASE WHEN ? != '' THEN ? ELSE nombre END WHERE wa_id = ?",
                (int(ts or time.time()), nombre, nombre, wa_id),
            )
            self._db.commit()

    def pausar(self, wa_id: str, segundos: int, motivo: str, ahora: int | None = None) -> int:
        """Calla al bot en ese chat. Nunca acorta una pausa ya puesta."""
        hasta = int(ahora or time.time()) + int(segundos)
        with self._candado:
            self._asegurar(wa_id)
            self._db.execute(
                "UPDATE chats SET pausado_hasta = MAX(pausado_hasta, ?), motivo_pausa = ?"
                " WHERE wa_id = ?",
                (hasta, motivo, wa_id),
            )
            self._db.commit()
        return hasta

    def reanudar(self, wa_id: str) -> None:
        with self._candado:
            self._asegurar(wa_id)
            self._db.execute(
                "UPDATE chats SET pausado_hasta = 0, motivo_pausa = '' WHERE wa_id = ?", (wa_id,)
            )
            self._db.commit()

    def pausado(self, wa_id: str, ahora: int | None = None) -> bool:
        return self.chat(wa_id)["pausado_hasta"] > int(ahora or time.time())

    def ventana_abierta(self, wa_id: str, ahora: int | None = None) -> bool:
        """True si el cliente escribió hace menos de 24 h (respuesta gratis)."""
        ultimo = self.chat(wa_id)["ultimo_entrante"]
        return bool(ultimo) and int(ahora or time.time()) - ultimo < VENTANA_SERVICIO_S

    def marcar_aviso_fuera_horario(self, wa_id: str, ahora: int | None = None) -> None:
        with self._candado:
            self._asegurar(wa_id)
            self._db.execute(
                "UPDATE chats SET aviso_fuera_horario = ? WHERE wa_id = ?",
                (int(ahora or time.time()), wa_id),
            )
            self._db.commit()

    def sumar_uso_ia(self, wa_id: str, dia: str) -> int:
        """Cuenta las respuestas con IA de ese chat en el día. Devuelve el total."""
        with self._candado:
            self._asegurar(wa_id)
            self._db.execute(
                "UPDATE chats SET ia_usos = CASE WHEN ia_dia = ? THEN ia_usos + 1 ELSE 1 END,"
                " ia_dia = ? WHERE wa_id = ?",
                (dia, dia, wa_id),
            )
            self._db.commit()
            fila = self._db.execute("SELECT ia_usos FROM chats WHERE wa_id = ?", (wa_id,)).fetchone()
        return int(fila["ia_usos"])

    def salientes_del_mes(self, ahora: int | None = None) -> int:
        """Mensajes que el bot ha mandado por la API este mes (hora de España).

        Desde el 1-oct-2026 Meta solo regala 1.000 mensajes de servicio al mes
        por número; con esto el bot sabe cuándo frenar.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        zona = ZoneInfo("Europe/Madrid")
        momento = datetime.fromtimestamp(int(ahora or time.time()), zona)
        inicio = int(momento.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        with self._candado:
            fila = self._db.execute(
                "SELECT COUNT(*) AS n FROM mensajes WHERE direccion = 'sale' AND ts >= ?", (inicio,)
            ).fetchone()
        return int(fila["n"])

    # ── vinculación en curso, datos sueltos y gasto de IA ───────────────────
    def poner_espera(self, wa_id: str, esperando: str = "", dato: str = "") -> None:
        with self._candado:
            self._asegurar(wa_id)
            self._db.execute(
                "UPDATE chats SET esperando = ?, dato_espera = ? WHERE wa_id = ?",
                (esperando, dato, wa_id),
            )
            self._db.commit()

    def dato(self, clave: str, defecto: str = "") -> str:
        with self._candado:
            fila = self._db.execute("SELECT valor FROM datos WHERE clave = ?", (clave,)).fetchone()
        return str(fila["valor"]) if fila else defecto

    def poner_dato(self, clave: str, valor: Any) -> None:
        with self._candado:
            self._db.execute(
                "INSERT OR REPLACE INTO datos (clave, valor) VALUES (?, ?)", (clave, str(valor))
            )
            self._db.commit()

    def anotar_ia(self, wa_id: str, modelo: str, entrada: int, salida: int, usd: float) -> None:
        with self._candado:
            self._db.execute(
                "INSERT INTO ia_llamadas (ts, wa_id, modelo, entrada, salida, usd)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (int(time.time()), wa_id, modelo, int(entrada), int(salida), float(usd)),
            )
            self._db.commit()

    def gasto_ia(self) -> dict[str, Any]:
        with self._candado:
            fila = self._db.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(usd), 0) AS usd FROM ia_llamadas"
            ).fetchone()
        return {"llamadas": int(fila["n"]), "usd": round(float(fila["usd"]), 6)}

    def mensajes_chat(self, wa_id: str, limite: int = 200) -> list[dict[str, Any]]:
        """Conversación entera (para el panel), del más antiguo al más nuevo."""
        return self.historial(wa_id, limite)

    def cerrar(self) -> None:
        with self._candado:
            self._db.close()
