"""Overlay de escudos de equipo en la intro (modo single_match).

Cuando el guion deep-dive de Champions menciona los dos equipos enfrentados
("entre el Arsenal y el Atlético de Madrid"), aparece el escudo del equipo
correspondiente a izquierda/derecha del frame durante unos segundos.

Asset opcional: `BIBLIOTECA_PRONOSTICOS_CLIPS/<carpeta_equipo>/escudo.png`
                 — cada carpeta de equipo puede llevar (o no) su escudo.

Layout (referencia visual del usuario):
- Escudo home en x ~27% del ancho (izquierda)
- Escudo away en x ~73% del ancho (derecha)
- Ambos a y ~43% del alto (zona alta-central, sobre la línea del campo)
- Tamaño: ~22% de la altura del frame
- Duración: 2.5s con fade de 0.15s
"""

from __future__ import annotations

from .stock_search import (
    _find_existing_folder, _slug_tokens, _normalize_token, _strip_accents,
)


def resolve_team_shield(team_name: str | None) -> str | None:
    """Devuelve path a `escudo.png` dentro de la carpeta del equipo, o None.

    Usa el mismo matcher fuzzy que stock_search (alias de tokens y acrónimos),
    así que 'Bayern München' encuentra `bayern_munich/escudo.png`.
    """
    if not team_name:
        return None
    folder = _find_existing_folder(team_name)
    if not folder:
        return None
    shield = folder / "escudo.png"
    return str(shield) if shield.exists() else None


def _norm_word(token: str) -> str:
    """Normaliza un token de Whisper igual que `_slug_tokens` normaliza folders."""
    base = _strip_accents((token or "").lower().strip(".,;:!?¡¿\"'() "))
    return _normalize_token(base)


def find_team_anchors(words: list[dict],
                       home_team: str | None,
                       away_team: str | None,
                       intro_end: float | None = None,
                       fallback_max_s: float = 25.0,
                       ) -> tuple[float | None, float | None]:
    """Devuelve `(home_anchor_s, away_anchor_s)`: primer timestamp donde se
    pronuncia un token DISTINTIVO de cada equipo.

    "Distintivo" = token que no comparten ambos equipos. Resuelve derbis tipo
    "Real Madrid vs Atlético Madrid" sin que `madrid` dispare ambos escudos
    a la vez (queda distinct_home={real}, distinct_away={atletico}).

    Estrategia de búsqueda en dos pasos:
      1. Hasta `intro_end` (preferido — el equipo se menciona "entre A y B").
      2. Si alguno no se halló, extiende hasta `fallback_max_s` para cubrir
         scripts donde los nombres caen dentro del primer pick (modo
         competition_focus repite el partido en cada pick).

    Si no se localiza un token, devuelve None para ese equipo.
    """
    home_tokens = _slug_tokens(home_team or "")
    away_tokens = _slug_tokens(away_team or "")
    distinct_home = home_tokens - away_tokens
    distinct_away = away_tokens - home_tokens
    # Si tras quitar tokens compartidos uno se queda vacío, usa el set completo
    # (caso degenerado: ambos equipos comparten todos los tokens — improbable).
    if not distinct_home:
        distinct_home = home_tokens
    if not distinct_away:
        distinct_away = away_tokens

    def _scan(limit_s: float | None) -> tuple[float | None, float | None]:
        h: float | None = None
        a: float | None = None
        for w in words or []:
            ts = float(w.get("start", 0))
            if limit_s is not None and ts >= limit_s:
                break
            token = _norm_word(w.get("word", ""))
            if not token:
                continue
            if h is None and token in distinct_home:
                h = ts
            elif a is None and token in distinct_away:
                a = ts
            if h is not None and a is not None:
                break
        return h, a

    home_anchor, away_anchor = _scan(intro_end)
    if home_anchor is None or away_anchor is None:
        h2, a2 = _scan(fallback_max_s)
        if home_anchor is None:
            home_anchor = h2
        if away_anchor is None:
            away_anchor = a2
    return home_anchor, away_anchor
