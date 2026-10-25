"""Vídeo hablado diario de C1, de punta a punta y sin tocar nada a mano.

Formato @analisis_yeison (oct-2026) con VARIOS partidos (3-4) en ~35 s y para
público de México: abre con «Tres partidazos este martes con la Champions League,
y te cuento cómo los vemos» (sin dinero desde el 25-oct: TikTok retiró un vídeo) mientras se ve una tarjeta blanca con todos los partidos (no
se leen en voz alta). Luego cada partido es UNA frase de contexto (resumen de su
`reason` de Redis con Gemini, sin inventar) + «Vamos con <UN pick>», con su
banda de marcador: «Arrancamos con…», el del medio sin conector, el CTA del
perfil y «Ya para cerrar con broche de oro, vemos que…». Así son los guiones de
Yeison (dos vídeos de referencia, 19-oct). Voz acelerada (`VELOCIDAD_VOZ`). Una
sola foto de fondo en todo el vídeo. Horas en hora de México.

1. **Picks**: los MISMOS del carrusel de mañana (`betai:daily_bets_tiktok:YYYY-MM`,
   campo = fecha): combinadas «viral» de 2 picks del mismo partido. El vídeo
   cuenta 3 de esos partidos (decisión del usuario, 14-oct). Nunca se inventa.
2. **Partidos**: los que tienen foto de equipo, luego 2 picks, luego cuota; se
   cuentan por hora de México. Una foto que no
   repita las de C1/C2 (`--evitar`). A mano: `--fixtures` y `--foto`.
3. **Guion**: plantilla (sin IA, así no se inventa nada). Números en letra
   para que la voz no los lea mal.
4. **Voz** con Fish (`VOCES`), **marcas** con Whisper (palabras
   «primero», «también», «segundo»…, «perfil», «guárdalo», buscadas
   EN ORDEN) y **montaje** con `video_hablado.renderizar`.

Salida en `--salida`: `video_hablado.mp4`, `guion.txt`, `titulo.txt`,
`descripcion.txt` y `meta.json` (fotos usadas, picks, voz…).

Se ejecuta dentro del contenedor `tiktok-api` (tiene Redis, Fish, Whisper y
ffmpeg); el envoltorio del host es `bet-ai-master/backend/tools/video_hablado_daily.sh`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from src.pronosticos.redis_client import UpstashRedis

FISH_TTS_URL = "https://api.fish.audio/v1/tts"
FISH_MODEL = os.environ.get("FISH_MODEL_VIDEO_HABLADO", "s2.1-pro-free")
FISH_USD_PER_MILLON_BYTES = 15.0
FONDOS_URL = "https://masterpicksai.com/api/backgrounds"
DRIVE = Path(os.environ.get("DRIVE_MOUNT", "/mnt/drive"))
CLIPS = DRIVE / "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS/BIBLIOTECA_PRONOSTICOS_CLIPS"

# Voces de Fish que pasaron el primer filtro (14-oct-2026). `f0` = tono medio.
VOCES = {
    # agudas / de mascota
    "dewey_juvenil": "a6339d4be17240debb46f284713bf3b3",     # 364 Hz
    "nono_animado": "60ad6b19c7f74257b865fecca881dd56",      # 432 Hz
    "el_dui": "37d28ffbfe0b483da35fef6c72ad70a6",            # 381 Hz
    "mascota_latino": "c6a522e89b5f415ca5c739fec95d128c",    # 381 Hz
    "dewey_nino": "feba84780b994df1b488b6fc1a65677e",        # 302 Hz
    "vos_tierna": "60525c84e0a142db9af4932408eca0cc",        # 291 Hz
    # graves / de viejo
    "viejo_anciano": "0324df2a5741462db69ceda5a6a7cce1",     # 129 Hz
    "esqueleto": "a335d470fff248e8890dce6550a2874b",         # 128 Hz
    "mascota_amigable": "e8c9e4c2c1e249e7807160f02ff6ccdf",  # 180 Hz
    "viejo_narrador2": "b625b5d09d834becb5ccfa0b20c9bc4a",   # 99 Hz
    # «Adam» de la biblioteca pública: la misma que usa @analisis_yeison (huella de voz 0,86-0,88, 22-oct)
    "adam2": "785d81f7fff943849fc0f077212f7cbd",
}
# Elegidas por el usuario: mascota el 14-oct-2026; viejo = adam2 desde el 22-oct (antes viejo_anciano).
VOZ_POR_DEFECTO = {"viejo": "adam2", "mascota": "dewey_juvenil"}
# Sin música de fondo (22-oct): el usuario la pone en TikTok. MUSICA_VIDEO_HABLADO=1 la vuelve a meter.
CON_MUSICA = os.environ.get("MUSICA_VIDEO_HABLADO", "") == "1"

# Gesto forzado en cada marca, por personaje. Al decir un pick el muñeco SEÑALA
# EL ESCUDO del equipo del pick en el marcador: local = izquierda (`izq`),
# visitante = derecha (`der`); si el pick es del partido entero, alterna.
GESTOS = {
    "viejo": {"izq": "senala_i", "der": "senala", "canal": "dedo_arriba", "guárdalo": "abre"},
    "mascota": {"izq": "senala_i", "der": "senala_d", "canal": "saluda_d", "guárdalo": "abre"},
}
ORDINALES = ["Primero", "Segundo", "Tercero", "Cuarto"]
NUMEROS = {2: "dos", 3: "tres", 4: "cuatro"}


def lado_pick(s: dict, c: dict, i: int) -> str:
    pick = _norm(s.get("pick", ""))
    for equipo, lado in ((c["visitante"], "der"), (c["local"], "izq")):
        slug = _slug_equipo(equipo)
        if slug and slug[:5] in pick:
            return lado
    return ["izq", "der"][i % 2]


# Público: México (14-oct-2026). Horas en CDMX y dinero en cifra redonda SIN
# nombrar moneda ni apuesta, como Yeison: «Cinco mil es lo que nos vamos a llevar…».
ZONA_REDIS, ZONA_PUBLICO = "Europe/Madrid", "America/Mexico_City"
LIGAS = {"UEFA Europa League": "la Europa League", "UEFA Champions League": "la Champions League",
         "UEFA Europa Conference League": "la Conference League", "CONMEBOL Libertadores": "la Libertadores",
         "CONMEBOL Sudamericana": "la Sudamericana", "La Liga": "LaLiga", "Premier League": "la Premier",
         "Serie A": "la Serie A", "Bundesliga": "la Bundesliga", "Ligue 1": "la Ligue 1"}
EUROPEAS = {"UEFA Europa League", "UEFA Champions League", "UEFA Europa Conference League", "La Liga",
            "Premier League", "Serie A", "Bundesliga", "Ligue 1", "Primeira Liga", "Eredivisie"}

# Sin «canal» ni «acceder» (25-oct): ofrecer acceso a picks es lo que TikTok castiga como servicio regulado.
CTA = "Antes de seguir, en nuestro perfil tienes más análisis como este."
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# Voz más rápida que la de Fish tal cual (pedido del usuario, 19-oct): atempo de ffmpeg, sin cambiar el tono.
VELOCIDAD_VOZ = float(os.environ.get("VELOCIDAD_VOZ_VIDEO_HABLADO", "1.12"))


# ---------------------------------------------------------------------------
# Números y picks en palabras
# ---------------------------------------------------------------------------
_U = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
      "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve",
      "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis",
      "veintisiete", "veintiocho", "veintinueve"]
_D = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta", 70: "setenta", 80: "ochenta", 90: "noventa"}
_C = {100: "ciento", 200: "doscientos", 300: "trescientos", 400: "cuatrocientos", 500: "quinientos",
      600: "seiscientos", 700: "setecientos", 800: "ochocientos", 900: "novecientos"}


def en_letra(n: int) -> str:
    """Entero 0-9999 en español (lo que hace falta para euros y líneas)."""
    if n < 30:
        return _U[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _D[d * 10] + (f" y {_U[u]}" if u else "")
    if n == 100:
        return "cien"
    if n < 1000:
        c, r = divmod(n, 100)
        return _C[c * 100] + (f" {en_letra(r)}" if r else "")
    m, r = divmod(n, 1000)
    return ("mil" if m == 1 else f"{en_letra(m)} mil") + (f" {en_letra(r)}" if r else "")


def num_hablado(x: str) -> str:
    v = float(x)
    if v.is_integer():
        return en_letra(int(v))
    ent, dec = str(v).split(".")
    return f"{en_letra(int(ent))} coma {en_letra(int(dec))}"


def pick_hablado(pick: str, local: str, visitante: str) -> str:
    p = pick.strip()
    low = p.lower()
    if low.startswith("victoria "):
        return f"gana el {_clave_equipo(p[9:].strip())}"
    if low.startswith("doble oportunidad"):
        resto = re.sub(r"\s+", " ", re.sub(r"(?i)doble oportunidad|empate|\so\s", " ", p)).strip()
        return f"el {_clave_equipo(resto)} no pierde"
    if low.startswith("ambos"):
        return "no marcan los dos equipos" if re.search(r"-\s*no\b|\bno$", low) else "marcan los dos equipos"
    m = re.match(r"(?i)^(?:([+-])|(más|menos) de)\s*(\d+(?:\.\d+)?)\s+(.+)$", p)
    if m:
        signo = "más de" if (m.group(1) == "+" or (m.group(2) or "").lower() == "más") else "menos de"
        cosa = m.group(4).strip()
        palabras = cosa.split()
        unidad, equipo = palabras[0].lower(), " ".join(palabras[1:])
        unidad = unidad.replace("corners", "córners")
        if equipo:
            return f"{signo} {num_hablado(m.group(3))} {unidad} del {_clave_equipo(equipo)}"
        return f"{signo} {num_hablado(m.group(3))} {unidad}"
    return re.sub(r"\d+(?:\.\d+)?", lambda mm: num_hablado(mm.group(0)), p)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def _horas_publico(t: str) -> dict:
    """«2026-10-15 18:45» (hora de España) → hora en México: corta («10:45»,
    para la tarjeta) y larga («10:45 a. m.», para la banda)."""
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.strptime(t[:16], "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(ZONA_REDIS))
    except ValueError:
        return {"hora": t[11:16], "hora_corta": t[11:16], "hora_mx": t[:16]}
    mx = dt.astimezone(ZoneInfo(ZONA_PUBLICO))
    h12 = mx.hour % 12 or 12
    return {"hora": f"{h12}:{mx:%M} {'a. m.' if mx.hour < 12 else 'p. m.'}", "hora_corta": f"{mx:%H:%M}",
            "hora_mx": f"{mx:%Y-%m-%d %H:%M}"}


def _hget_json(r: UpstashRedis, key: str, campo: str):
    v = r.hget(key, campo)
    if not v:
        return None
    return json.loads(v) if isinstance(v, str) else v


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"[^a-z0-9.+-]", "", "".join(c for c in s if not unicodedata.combining(c)))


def candidatos(fecha: str, r: UpstashRedis | None = None) -> list[dict]:
    """Partidos del carrusel de `fecha` con sus picks (máx. 2, sin inventar)."""
    r = r or UpstashRedis()
    mes = fecha[:7]
    tk = _hget_json(r, f"daily_bets_tiktok:{mes}", fecha)
    if not tk:
        raise SystemExit(f"No hay carrusel de TikTok para {fecha} en Redis (daily_bets_tiktok:{mes}).")
    extra: dict[int, list[dict]] = {}
    for key in (f"daily_bets:{mes}", f"daily_bets_stakazo:{mes}"):
        d = _hget_json(r, key, fecha) or {}
        for b in d.get("bets", []):
            for s in b.get("selections") or []:
                if s.get("fixture_id"):
                    extra.setdefault(int(s["fixture_id"]), []).append(s)
    out = []
    for b in tk.get("bets", []):
        sels = [s for s in (b.get("selections") or []) if s.get("fixture_id")]
        if not sels:
            continue
        fid = int(sels[0]["fixture_id"])
        if any(int(s["fixture_id"]) != fid for s in sels):
            continue   # combinada de varios partidos: no es formato Yeison
        picks, vistos = [], set()
        for s in sels:   # SOLO los picks del carrusel (mismos que C1/C2), nada de otros pronósticos
            k = _norm(s.get("pick", ""))
            if k and k not in vistos:
                vistos.add(k)
                picks.append(s)
        picks = picks[:2]
        local, _, visitante = sels[0]["match"].partition(" vs ")
        out.append({
            "fixture_id": fid, "local": local.strip(), "visitante": visitante.strip(),
            "liga": sels[0].get("league", ""), "hora_es": (sels[0].get("time") or "")[11:16],
            **_horas_publico(sels[0].get("time") or ""),
            "logo_local": sels[0].get("home_logo"), "logo_visitante": sels[0].get("away_logo"),
            "picks": picks, "reason": b.get("reason", ""), "titulo": b.get("match", ""),
            "cuota": round(math.prod(float(s.get("odd") or 1) for s in picks), 2),
        })
    return out


_AFIJOS = re.compile(r"^(fc|cf|sc|ac|as|ss|ca|cd|ud|rc|rcd|sl|afc|1fc)|(fc|cf|sc|ac|calcio|club)$")


def _slug_equipo(s: str) -> str:
    return _AFIJOS.sub("", _norm(s.split("(")[0]).replace(".", "").replace("-", "").replace("+", ""))


def fotos_de(equipo: str, todas: list[str]) -> list[str]:
    slug = _slug_equipo(equipo)
    res = []
    for url in todas:
        nombre = url.split("/")[-1]
        partes = nombre.split("-")
        if not nombre.startswith("bg-futbol-") or len(partes) < 4 or "comodin" in nombre or "portada" in nombre:
            continue
        if len(slug) >= 3 and _slug_equipo(partes[2]) == slug:
            res.append(url)
    return res


# Clubes que más enganchan en México/LATAM y España (para elegir los 3 del vídeo).
GRANDES = {"realmadrid", "barcelona", "atleticomadrid", "milan", "inter", "juventus", "napoli", "roma",
           "psg", "parissaintgermain", "bayernmunchen", "bayernmunich", "borussiadortmund", "manchestercity",
           "manchesterunited", "liverpool", "arsenal", "chelsea", "tottenham", "benfica", "porto", "ajax",
           "bocajuniors", "riverplate", "flamengo", "palmeiras", "america", "chivas", "guadalajara",
           "cruzazul", "tigres", "monterrey", "pumas", "sevilla", "realbetis", "villarreal", "athleticclub",
           "realsociedad", "celtavigo", "celta", "bayerleverkusen", "intermiami"}


def _tirón(c: dict) -> int:
    """2 si juegan dos grandes, 1 si uno, 0 si ninguno."""
    return sum(_slug_equipo(c[k]) in GRANDES for k in ("local", "visitante"))


def elegir(cands: list[dict], todas: list[str], evitar: set[str], n: int = 3) -> tuple[list[dict], str | None]:
    """Los `n` partidos del vídeo (por hora de inicio) y UNA foto para todo el
    vídeo (Yeison usa una sola), del equipo más arriba en el orden de elección.
    Salen de los 6-7 del carrusel: primero los que tienen foto y clubes grandes.
    Las horas de madrugada en España son la tarde de antes en México: valen."""
    usadas = set(evitar)

    def fotos(c):
        return [f for f in fotos_de(c["local"], todas) + fotos_de(c["visitante"], todas)
                if f.split("/")[-1] not in usadas]

    orden = sorted(cands, key=lambda c: (bool(fotos(c)), _tirón(c), len(c["picks"]) >= 2, c["cuota"]),
                   reverse=True)[:n]
    foto = next((fotos(c)[0] for c in orden if fotos(c)), None)
    return sorted(orden, key=lambda c: c["hora_mx"]), foto


NOMBRE_CORTO = {
    "boca juniors": "Boca", "river plate": "River", "argentinos juniors": "Argentinos",
    "eintracht frankfurt": "Frankfurt", "racing club": "Racing",
    "manchester city": "City", "manchester united": "United", "atletico madrid": "Atlético",
    "atletico de madrid": "Atlético", "real madrid": "Madrid", "paris saint germain": "PSG",
    "bayern": "Bayern", "inter milan": "Inter", "ac milan": "Milan", "borussia dortmund": "Dortmund",
    "rayo vallecano": "Rayo", "aek athens fc": "AEK", "aek athens": "AEK", "gil vicente": "Gil Vicente",
}


def _clave_equipo(nombre: str) -> str:
    """Nombre corto para decirlo (y que Whisper lo reconozca): la palabra más
    larga, sin «Red Bull», «AC», «Vigo»… («Leverkusen», no «Bayer»). Los que la
    afición llama de otra forma van en NOMBRE_CORTO («Boca», no «Juniors»)."""
    for clave, corto in NOMBRE_CORTO.items():
        if clave in nombre.lower():
            return corto
    palabras = [w for w in re.findall(r"\w+", nombre.split("(")[0]) if w.lower() not in ("red", "bull", "vigo")]
    return max(palabras or [nombre], key=len)


def cantidad(cuota: float) -> int:
    """Cifra redonda de 5.000 a 10.000 (pesos, sin decirlo) que sale de la cuota
    total con una apuesta de 500, 1.000 o 2.000 (que no se dice)."""
    for base in (1000, 2000, 500):
        x = int(cuota * base // 1000 * 1000)
        if 5000 <= x <= 10000:
            return x
    return min(10000, max(5000, int(cuota * 1000 // 1000 * 1000)))


def apertura(partidos: list[dict], fecha: str) -> str:
    """«Tres partidazos este martes con la Champions League, y te cuento cómo los vemos.»
    (la mayoría, 2 de 3, de la misma competición conocida; pedido del usuario el
    19-oct) o «… con esta jornada del lunes …».
    Antes abría con la cifra de Yeison («Cinco mil es lo que nos vamos a llevar…»), pero
    TikTok retiró el vídeo del Clásico (82k visitas, 25-oct) por «bienes y servicios
    regulados»: nada de dinero ni ganancias en la voz."""
    from collections import Counter
    n = NUMEROS.get(len(partidos), str(len(partidos)))
    dia = DIAS[date.fromisoformat(fecha).weekday()]
    liga, veces = Counter(c["liga"] for c in partidos).most_common(1)[0]
    if liga in LIGAS and veces * 2 > len(partidos):
        cola = f"este {dia} con {LIGAS[liga]}"
    else:
        cola = f"con esta jornada del {dia}"
    return f"{n.capitalize()} partidazos {cola}, y te cuento cómo los vemos."


def pick_vamos(pick: str, local: str, visitante: str) -> str:
    """El pick como lo dice Yeison detrás de «Vamos con…»."""
    h = pick_hablado(pick, local, visitante)
    if h.startswith("gana el "):
        return f"la victoria del {h[8:]}"
    if h.startswith(("más de", "menos de")):
        return h if " del " in h else f"{h} en el partido"
    return f"que {h}"


ROLES = {0: "inicio", -1: "cierre"}
_SISTEMA_CONTEXTO = """Escribes guiones de TikTok de pronósticos de fútbol para público de México, con el estilo del creador @analisis_yeison.
Para cada partido recibes los dos equipos (con el nombre que debes usar), el pronóstico que se dirá DESPUÉS de tu frase y un análisis.
Escribe UNA frase de contexto por partido que justifique ese pronóstico, sacada SOLO del análisis.
Reglas:
- No inventes nada que no esté en el análisis (ni lesiones, ni posiciones en la tabla, ni rachas, ni resultados, ni cifras).
- Entre 10 y 16 palabras. Habla como un amigo que sabe de fútbol contándolo en voz alta: palabras de la calle, nada de jerga de analista (prohibido «ejercerá», «volumen», «fricción», «transiciones», «bloque bajo», «verticalidad», «inercia»). Español neutro de México. Sin cifras, sin porcentajes, sin cuotas, sin emojis.
- Una idea por frase, la más clara del análisis (quién llega mejor, quién ataca, quién se cierra, si habrá goles o no).
- Usa los nombres de los equipos EXACTAMENTE como te los dan. No digas el pronóstico (se dice después). Sin punto final.
- rol "inicio": empieza por el nombre de un equipo (o «<local> y <visitante>» si hablas de los dos) seguido de ", que" (va detrás de «Arrancamos con»). Ej.: "Tottenham, que está pasando por su peor momento, con grandes problemas en defensa" o "PSG y Barcelona, que llegan con los dos ataques encendidos"
- rol "medio": frase completa con mayúscula inicial. Ej.: "Bodo Glimt en casa se hace muy fuerte, mientras que al Dortmund fuera le cuesta mucho y cede muchos espacios"
- rol "cierre": empieza por "vemos que" en minúscula (va detrás de «Ya para cerrar con broche de oro,»). Ej.: "vemos que ambos equipos llegan en un buen estado de forma y aquí la localía podría marcar la diferencia"
Devuelve JSON: {"frases": ["...", "..."]} en el mismo orden."""


def contextos(partidos: list[dict], corto: list[tuple[str, str]]) -> list[str]:
    """Una frase de contexto por partido (Gemini resume su `reason`; si falla, una genérica)."""
    n = len(partidos)
    roles = [ROLES.get(k, ROLES[-1] if k == n - 1 else "medio") for k in range(n)]
    datos = [{"equipos": list(corto[k]), "pronostico": pick_vamos(c["picks"][0]["pick"], c["local"], c["visitante"]),
              "rol": roles[k], "analisis": c.get("reason", "")} for k, c in enumerate(partidos)]
    frases: list[str] = []
    try:
        from src.tiktok_shop.api.gemini import generate_json
        res = generate_json(_SISTEMA_CONTEXTO, json.dumps(datos, ensure_ascii=False), temperature=0.5,
                            max_output_tokens=4096)
        frases = [str(f).strip().rstrip(".") for f in (res.get("frases") or [])]
    except Exception as e:
        print(f"[guion] Gemini falló ({e}); uso frases genéricas")
    out = []
    for k, (l, v) in enumerate(corto):
        f = frases[k] if k < len(frases) and frases[k] else ""
        rol = roles[k]
        if rol == "inicio" and not (f.startswith(l) or f.startswith(v)):
            f = f"{l} contra {v}, un partido que pinta muy bien para lo nuestro"
        elif rol == "cierre":
            if not f:
                f = f"vemos que el {l} contra {v} pinta muy bien para lo nuestro"
            elif not f.lower().startswith("vemos que"):
                f = "vemos que " + f[0].lower() + f[1:]
            else:
                f = "v" + f[1:]
        elif rol == "medio" and not f:
            f = f"En el {l} contra {v} lo tenemos claro"
        out.append(f)
    return out


def guion(partidos: list[dict], fecha: str) -> tuple[str, list[tuple[str, str, int | None]]]:
    """Texto del vídeo y sus marcas en orden: (palabra(s) clave, gesto, escena o None).

    Escena 0 = tarjeta con todos los partidos (desde el principio); la escena
    k+1 (banda del partido k) entra al empezar su frase de contexto. Un solo
    pick por partido (el primero del carrusel), dicho tras «Vamos con»."""
    n = len(partidos)
    for c in partidos:
        c["cuota_dicha"] = float(c["picks"][0].get("odd") or c["cuota"])
    corto = [(_clave_equipo(c["local"]), _clave_equipo(c["visitante"])) for c in partidos]
    ctx = contextos(partidos, corto)
    frases = [apertura(partidos, fecha)]
    claves: list[tuple[str, str, int | None]] = []
    for k, c in enumerate(partidos):
        pick = pick_vamos(c["picks"][0]["pick"], c["local"], c["visitante"])
        if k == 0:
            frases.append(f"Arrancamos con {ctx[k]}.")
            claves.append(("arrancamos", "", 1))
        elif k == n - 1 and n > 1:
            frases.append(f"Ya para cerrar con broche de oro, {ctx[k]}.")
            claves.append(("broche", "guárdalo", k + 1))
        else:
            frases.append(f"{ctx[k]}.")
            claves.append((" ".join(ctx[k].split()[:2]), "", k + 1))
        frases.append(f"Vamos con {pick}.")
        claves.append(("vamos", f"pick:{k}:0", None))
        if k == n - 2:
            frases.append(CTA)
            claves.append(("perfil", "canal", None))
    return " ".join(frases), claves


# ---------------------------------------------------------------------------
# Voz, marcas y montaje
# ---------------------------------------------------------------------------
def locutar(texto: str, voz: str, salida: str) -> None:
    ref = VOCES.get(voz, voz)
    cuerpo = json.dumps({"text": texto, "reference_id": ref, "format": "mp3", "normalize": True}).encode()
    req = urllib.request.Request(FISH_TTS_URL, data=cuerpo, headers={
        "Authorization": f"Bearer {os.environ['FISH_API_KEY']}", "Content-Type": "application/json",
        "model": FISH_MODEL})
    import time
    for intento in range(4):   # Fish devuelve 429/5xx de vez en cuando con varias seguidas
        try:
            Path(salida).write_bytes(urllib.request.urlopen(req, timeout=240).read())
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if intento == 3:
                raise
            print(f"[voz] Fish falló ({e}); reintento en {5 * 2 ** intento} s")
            time.sleep(5 * 2 ** intento)
    if abs(VELOCIDAD_VOZ - 1.0) > 0.01:
        import subprocess
        tmp = salida + ".lenta.mp3"
        os.replace(salida, tmp)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-filter:a", f"atempo={VELOCIDAD_VOZ}",
                        "-b:a", "192k", salida], check=True)
        os.remove(tmp)
    try:
        from src import cost_tracking
        b = len(texto.encode("utf-8"))
        cost_tracking.record_custom(kind="fish_tts", units=b, unit_label="bytes",
                                    cost_usd=0.0 if FISH_MODEL.endswith("-free") else b / 1e6 * FISH_USD_PER_MILLON_BYTES,
                                    detail=f"{FISH_MODEL} · {voz} · video_hablado")
    except Exception:
        pass


def marcas_whisper(audio: str, texto: str, claves: list[tuple[str, str, int | None]]) -> list[tuple[float, str, int | None]]:
    """Segundo en que se dice cada palabra clave, buscándolas EN ORDEN (la misma
    palabra puede salir varias veces). Si Whisper no la oye, se estima por su
    posición en el texto."""
    from faster_whisper import WhisperModel
    import subprocess
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio],
                               capture_output=True, text=True).stdout.strip() or 0)
    m = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language="es", word_timestamps=True)
    oidas = [(_norm(w.word), w.start) for s in segs for w in s.words]
    escritas = [_norm(w) for w in texto.split()]
    res, io, ie, t_prev = [], 0, 0, 0.0
    palabras_oidas = [w for w, _ in oidas]

    def casa(lista: list[str], x: int, ks: list[str]) -> bool:
        """¿Empiezan en `x` las palabras clave seguidas? (prefijo de 6 letras de cada una)"""
        return x + len(ks) <= len(lista) and all(lista[x + i].startswith(kk) for i, kk in enumerate(ks))

    for clave, gesto, escena in claves:
        ks = [_norm(w)[:6] for w in clave.split() if _norm(w)] or [""]
        j = next((x for x in range(io, len(oidas)) if casa(palabras_oidas, x, ks)), None)
        je = next((x for x in range(ie, len(escritas)) if casa(escritas, x, ks)), None)
        if je is not None:
            ie = je + 1
        if j is not None:
            io, t = j + 1, oidas[j][1]
        else:
            t = dur * (je if je is not None else ie) / max(1, len(escritas))
        t = max(t, t_prev)
        t_prev = t
        res.append((round(t, 2), gesto, escena))
    return res


def textos_tiktok(partidos: list[dict], out: Path, fecha: str, r: UpstashRedis | None = None) -> None:
    """Solo descripcion.txt (el vídeo no lleva título): la caption de C1 (versión sin
    emojis de `tiktokfactory_tomorrow`) recortada a los partidos del vídeo, en su orden.
    Nada de apuestas ni hashtags (lo pidió el usuario el 15-oct)."""
    n = NUMEROS.get(len(partidos), str(len(partidos)))
    try:
        soc = (r or UpstashRedis()).get("tiktokfactory_tomorrow")
        soc = json.loads(soc) if isinstance(soc, str) else soc or {}
    except Exception:
        soc = {}
    vers = soc.get("versions") or []
    ver = (vers[1] if len(vers) > 1 else vers[0] if vers else {}) if soc.get("date") == fecha else {}
    texto = re.sub(r"(?<!\S)#\w+", "", ver.get("content", ""))   # sin hashtags, también los de dentro de un párrafo
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    bloques = [b.strip() for b in texto.strip().split("\n\n") if b.strip()]
    if bloques:   # titular de la IA («EL RADAR TÁCTICO…»), suelto o pegado al primer párrafo
        primera, _, resto = bloques[0].partition("\n")
        letras = [c for c in primera if c.isalpha()]
        gritado = len(letras) >= 6 and sum(c.isupper() for c in letras) / len(letras) > 0.7
        titular = _norm(primera) == _norm(ver.get("title", "")) or (
            len(primera) < 100 and " vs " not in primera and gritado)
        if titular:
            bloques = ([resto.strip()] if resto.strip() else []) + bloques[1:]
    es_partido = [" vs " in b.split("\n")[0] for b in bloques]

    def claves_de(c: dict) -> list[str]:
        ks = [_norm(_clave_equipo(c["local"]))]
        ks += [_norm(w) for w in re.findall(r"\w+", c["local"].split("(")[0]) if len(w) >= 4]
        return [k for k in ks if k]

    elegidos = []
    for c in partidos:
        ks = claves_de(c)
        b = next((b for b, p in zip(bloques, es_partido)
                  if p and any(k in _norm(b.split("\n")[0]).replace("-", "") for k in ks)), None)
        if b:
            elegidos.append(b)
    if len(elegidos) == len(partidos) and any(es_partido):
        primero = es_partido.index(True)
        ultimo = len(es_partido) - 1 - es_partido[::-1].index(True)
        intro = [re.sub(r"\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b", n, b, count=1)
                 for b in bloques[:primero]]
        desc = "\n\n".join(intro + elegidos + bloques[ultimo + 1:])
        # la caption de la IA a veces se equivoca de día («este viernes» para un sábado)
        dia = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[date.fromisoformat(fecha).weekday()]
        desc = re.sub(r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b", dia, desc)
    else:   # sin caption de esa fecha: lista sencilla
        desc = f"{n.capitalize()} partidos para mañana:\n" + \
               "\n".join(f"{c['local']} vs {c['visitante']} · {c['hora']}" for c in partidos)
    (out / "descripcion.txt").write_text(desc + "\n", encoding="utf-8")


def _bajar(url: str, destino: Path) -> Path:
    if not url.startswith("http"):
        destino.write_bytes(Path(url).read_bytes())
        return destino
    destino.write_bytes(requests.get(url, timeout=60).content)
    return destino


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fecha", help="fecha de los partidos (por defecto, mañana)")
    ap.add_argument("--personaje", choices=["viejo", "mascota"], default="viejo")
    ap.add_argument("--voz", help=f"nombre de VOCES o reference_id de Fish (por defecto {VOZ_POR_DEFECTO})")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--evitar", default="", help="fotos ya usadas hoy (nombres separados por comas)")
    ap.add_argument("--partidos", type=int, default=3, help="cuántos partidos cuenta (3-4)")
    ap.add_argument("--fixtures", help="partidos elegidos a mano (fixture_id separados por comas, en orden)")
    ap.add_argument("--foto", help="foto de fondo elegida a mano, una para todo el vídeo (URL o ruta)")
    ap.add_argument("--listar", action="store_true", help="lista partidos candidatos y sus fotos, y sale")
    ap.add_argument("--solo-guion", action="store_true", help="imprime el guion y no gasta nada más")
    ap.add_argument("--voces", help="en vez de vídeo, locutar el guion con estas voces (coma) para elegir")
    a = ap.parse_args()

    fecha = a.fecha or (date.today() + timedelta(days=1)).isoformat()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    cands = candidatos(fecha)
    todas = [u if u.startswith("http") else "https://masterpicksai.com" + u
             for u in requests.get(FONDOS_URL, timeout=30).json().get("files", [])]
    if a.listar:
        for k in cands:
            fs = fotos_de(k["local"], todas) + fotos_de(k["visitante"], todas)
            print(json.dumps({"fixture_id": k["fixture_id"], "partido": f"{k['local']} vs {k['visitante']}",
                              "picks": [s["pick"] for s in k["picks"]], "cuota": k["cuota"], "hora": k["hora"],
                              "fotos": fs}, ensure_ascii=False))
        return
    evitar = {x for x in a.evitar.split(",") if x}
    if a.fixtures:
        por_id = {c["fixture_id"]: c for c in cands}
        ids = [int(x) for x in a.fixtures.split(",") if x]
        faltan = [x for x in ids if x not in por_id]
        if faltan:
            raise SystemExit(f"Esos fixtures no están en el carrusel de {fecha}: {faltan}")
        partidos = [por_id[x] for x in ids]
        foto = elegir(partidos, todas, evitar, len(ids))[1]
    else:
        partidos, foto = elegir(cands, todas, evitar, a.partidos)
    foto = a.foto or foto
    if len(partidos) < 2 or not foto:
        raise SystemExit("Faltan partidos o foto en /api/backgrounds: súbela en /admin (tiktok-fotos) o usa --foto.")
    for c in partidos:
        print(f"[partido] {c['hora']} (México) {c['local']} vs {c['visitante']} · {[s['pick'] for s in c['picks']]}")
    print(f"[foto] {foto}")
    texto, claves = guion(partidos, fecha)
    (out / "guion.txt").write_text(texto + "\n", encoding="utf-8")
    print(f"[guion] {len(texto.split())} palabras · {texto}")
    if a.solo_guion:
        return
    if a.voces:
        for v in a.voces.split(","):
            locutar(texto, v, str(out / f"{v}.mp3"))
            print(f"[voz] {v}")
        return

    voz = a.voz or VOZ_POR_DEFECTO[a.personaje]
    audio = out / "voz.mp3"
    locutar(texto, voz, str(audio))
    marcas_t = marcas_whisper(str(audio), texto, claves)
    print(f"[marcas] {marcas_t}")
    g = GESTOS[a.personaje]
    marcas, inicios = [], {0: 0.0}
    for t, gesto, escena in marcas_t:
        if escena is not None:
            inicios[escena] = max(0.0, t - 0.15)
        if gesto.startswith("pick:"):
            _, k, i = gesto.split(":")
            c = partidos[int(k)]
            marcas.append((t, g[lado_pick(c["picks"][int(i)], c, int(i))]))
        elif gesto:
            marcas.append((t, g[gesto]))

    tmp = out / "_tmp"
    tmp.mkdir(exist_ok=True)
    fondo = str(_bajar(foto, tmp / "fondo.jpg"))
    filas = []
    for k, c in enumerate(partidos):
        filas.append({"logo_l": str(_bajar(c["logo_local"], tmp / f"l{k}.png")),
                      "logo_v": str(_bajar(c["logo_visitante"], tmp / f"v{k}.png")),
                      "local": c["local"], "visitante": c["visitante"],
                      "hora": c["hora"], "hora_corta": c["hora_corta"]})
    escenas = [{"t": 0.0, "fondo": fondo, "lista": filas}] + \
              [{**filas[k - 1], "t": inicios[k], "fondo": fondo} for k in sorted(inicios) if k]

    from src.pronosticos.video_hablado import renderizar
    if a.personaje == "mascota":
        from src.pronosticos.rig_mascota import PersonajeMascota
        pj = PersonajeMascota(str(CLIPS / "munecos" / "mascota"))
    else:
        from src.pronosticos.rig_hablado import PersonajeViejo
        pj = PersonajeViejo()
    musica = CLIPS / "sfx" / "fondo.mp3"
    alturas = renderizar(str(audio), escenas, pj, str(out / "video_hablado.mp4"), marcas=marcas,
                         musica=str(musica) if CON_MUSICA and musica.exists() else None,
                         semilla=int(fecha.replace("-", "")) % 997)
    textos_tiktok(partidos, out, fecha)
    (out / "meta.json").write_text(json.dumps({
        "fecha": fecha, "generado": datetime.now().isoformat(timespec="seconds"),
        "partidos": [{"partido": f"{c['local']} vs {c['visitante']}", "fixture_id": c["fixture_id"],
                      "hora_mexico": c["hora"], "picks": [s["pick"] for s in c["picks"]]} for c in partidos],
        "fotos": [foto.split("/")[-1]], "personaje": a.personaje, "voz": voz,
        "marcas": marcas, "escenas": [round(e["t"], 2) for e in escenas], "marcador_y": alturas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    audio.unlink()
    print(f"[ok] {out / 'video_hablado.mp4'}")


if __name__ == "__main__":
    main()
