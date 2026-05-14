"""Orquestador del flujo del usuario.

Recibe la lista de `ToolStep` configurada por el usuario y la ejecuta
secuencialmente en el ORDEN CORRECTO (no el orden en que el usuario las
añadió). El reordenamiento es determinista por `position_weight` del
registry, definido en `config.TOOL_POSITION_WEIGHTS`.

Por qué regla fija y no IA:
  - Las dependencias entre herramientas son técnicas, no semánticas:
    cortar silencios DEBE ir antes que añadir overlays porque mueve
    timestamps. Una IA aquí solo añade latencia y un punto de fallo.
  - Cuando añadamos más herramientas (zoom, color grading, etc.) cada
    una declara su peso en TOOL_POSITION_WEIGHTS — sin tocar este file.
"""

from __future__ import annotations

import os
import shutil
from typing import Callable

from src.editor_auto.config import (
    DEFAULT_TOOL_WEIGHT,
    TOOL_POSITION_WEIGHTS,
    TOOL_SILENCE_CUTTER_SCRIPTED,
)
from src.editor_auto.models import EditorUser, ToolStep
from src.editor_auto.tools import REGISTRY, get_tool
from src.editor_auto.tools.base import ToolContext


LogFn = Callable[[str], None]
ProgressFn = Callable[[float, str], None]


def order_steps(steps: list[ToolStep]) -> list[ToolStep]:
    """Devuelve los pasos habilitados ordenados por `position_weight`.

    Pasos con tool_id desconocido se mantienen al final (no se ejecutarán
    porque el runner los saltará) — la UI puede mostrarlos como warning.
    """
    def weight_of(s: ToolStep) -> int:
        if s.tool_id not in REGISTRY:
            return 999  # tools desconocidos al final
        return TOOL_POSITION_WEIGHTS.get(s.tool_id, DEFAULT_TOOL_WEIGHT)

    enabled = [s for s in steps if s.enabled]
    return sorted(enabled, key=weight_of)


def run_flow(
    *,
    user: EditorUser,
    job_id: str,
    input_video_path: str,
    final_output_path: str,
    temp_folder: str,
    on_log: LogFn,
    on_progress: ProgressFn,
    script: str | None = None,
) -> str:
    """Ejecuta el flujo completo del usuario sobre `input_video_path` y
    deja el resultado en `final_output_path`.

    Cada herramienta recibe un sub-rango del progreso global [0..1]
    repartido uniformemente. La última herramienta escribe directamente
    en `final_output_path`; las intermedias usan archivos temporales.

    Si el flujo no tiene herramientas habilitadas, copia el input al
    output sin tocar nada (no se enviaría a la cola en ese caso, pero
    por defensiva).
    """
    ordered = order_steps(user.tool_flow)
    if not ordered:
        on_log("[orchestrator] Flujo vacío → copia directa input → output")
        shutil.copyfile(input_video_path, final_output_path)
        on_progress(1.0, "✅ Sin herramientas — passthrough")
        return final_output_path

    n = len(ordered)
    on_log(f"[orchestrator] Ejecutando {n} herramienta(s) en orden:")
    for i, step in enumerate(ordered):
        tool = get_tool(step.tool_id)
        name = tool.display_name if tool else f"<desconocido:{step.tool_id}>"
        on_log(f"  {i+1}. {name} (peso {_weight_label(step.tool_id)})")

    current_input = input_video_path
    temp_outputs: list[str] = []

    try:
        for i, step in enumerate(ordered):
            tool = get_tool(step.tool_id)
            if tool is None:
                on_log(
                    f"[orchestrator] ⚠️ Tool '{step.tool_id}' no registrado, "
                    f"saltando."
                )
                continue

            slot_lo = i / n
            slot_hi = (i + 1) / n

            def _sub_progress(frac: float, msg: str, *, _lo=slot_lo, _hi=slot_hi) -> None:
                frac = max(0.0, min(1.0, frac))
                on_progress(_lo + (_hi - _lo) * frac, msg)

            # Última herramienta → escribe en `final_output_path`. Resto
            # usan archivos temporales numerados para auditoría.
            if i == n - 1:
                step_output = final_output_path
            else:
                step_output = os.path.join(
                    temp_folder,
                    f"editor_step_{job_id}_{i:02d}_{step.tool_id}.mp4",
                )
                temp_outputs.append(step_output)

            on_log(f"[orchestrator] ▶ {tool.display_name} → {os.path.basename(step_output)}")
            _sub_progress(0.0, f"▶ {tool.display_name}…")

            # Merge config: defaults + lo guardado en el step (override) +
            # inyección per-job. El guion del job se inyecta SOLO en la
            # tool scripted — el resto lo ignora.
            merged_config = {**tool.default_config(), **(step.config or {})}
            if step.tool_id == TOOL_SILENCE_CUTTER_SCRIPTED and script:
                merged_config["script"] = script

            ctx = ToolContext(
                user_id=user.id,
                user_name=user.name,
                job_id=job_id,
                temp_folder=temp_folder,
                on_log=on_log,
                on_progress=_sub_progress,
            )
            result_path = tool.run(
                input_path=current_input,
                output_path=step_output,
                config=merged_config,
                ctx=ctx,
            )
            current_input = result_path

        on_progress(1.0, "✅ Flujo completado")
        return current_input
    finally:
        # Limpieza de temporales intermedios
        for p in temp_outputs:
            try:
                if os.path.exists(p) and p != current_input:
                    os.remove(p)
            except OSError:
                pass


def _weight_label(tool_id: str) -> int:
    return TOOL_POSITION_WEIGHTS.get(tool_id, DEFAULT_TOOL_WEIGHT)
