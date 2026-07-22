#!/usr/bin/env python3
"""Genera MUESTRAS de edición por lote desde la terminal (Nebulabs Media).

Caso de uso: captación manual de clientes de TikTok Shop. Metes en una carpeta
los vídeos de N creadores, lanzas un comando, y salen editados a una carpeta
local listos para mandar por DM ("te lo he reeditado gratis, quédatelo").

Reutiliza el MISMO motor que la web/cola (`run_editor_auto_pipeline`), así que
la muestra sale con la calidad real del producto — no es un mock.

Uso:
    # 1) Ver qué estilos (EditorUser) hay configurados:
    python -m scripts.editor_auto.batch_samples --list

    # 2) Procesar una carpeta con un estilo concreto:
    python -m scripts.editor_auto.batch_samples \
        --user-id <ID_DEL_ESTILO> \
        --in  ./muestras_in \
        --out ./muestras_out

Requisitos: correr dentro del entorno del proyecto (venv de tiktok-factory:
deps instaladas + .env con Redis/Drive), porque el motor toca Redis y el mount.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

# Permite `python scripts/editor_auto/batch_samples.py` además de `-m`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _list_styles() -> int:
    from src.editor_auto.repos.user_repo import UserRepo

    users = UserRepo().list_all()
    if not users:
        print("No hay ningún EditorUser (estilo) configurado todavía.")
        print("Crea uno desde la UI (Editor Auto) o pide que se cree un estilo "
              "'muestras' con subs_auto + silence_cutter.")
        return 1
    print(f"{'ID':<34} {'NOMBRE':<22} HERRAMIENTAS (flujo activo)")
    print("-" * 90)
    for u in users:
        tools = [s.tool_id for s in u.tool_flow if s.enabled]
        review = "  [manual_review ON]" if getattr(u, "manual_review", False) else ""
        print(f"{u.id:<34} {(u.display_name or u.name)[:22]:<22} "
              f"{', '.join(tools) or '(sin herramientas)'}{review}")
    print()
    print("Elige el ID del estilo que quieras para las muestras y pásalo con --user-id.")
    return 0


def _run_batch(user_id: str, in_dir: str, out_dir: str) -> int:
    from src.editor_auto.pipeline import run_editor_auto_pipeline

    if not os.path.isdir(in_dir):
        print(f"ERROR: la carpeta de entrada no existe: {in_dir}")
        return 1
    os.makedirs(out_dir, exist_ok=True)
    temp_root = os.path.abspath(os.path.join(out_dir, "_tmp"))
    os.makedirs(temp_root, exist_ok=True)

    videos = sorted(
        os.path.join(in_dir, f) for f in os.listdir(in_dir)
        if os.path.splitext(f)[1].lower() in _VIDEO_EXTS
    )
    if not videos:
        print(f"No hay vídeos ({', '.join(sorted(_VIDEO_EXTS))}) en {in_dir}")
        return 1

    print(f"Estilo (user_id): {user_id}")
    print(f"Entrada: {in_dir}  ·  {len(videos)} vídeo(s)")
    print(f"Salida:  {out_dir}")
    print("=" * 70)

    ok: list[str] = []
    fail: list[tuple[str, str]] = []

    for idx, src in enumerate(videos, 1):
        stem = os.path.splitext(os.path.basename(src))[0]
        out_path = os.path.abspath(os.path.join(out_dir, f"{stem}_muestra.mp4"))
        job_id = f"sample_{uuid.uuid4().hex[:8]}"
        temp_folder = os.path.join(temp_root, job_id)
        os.makedirs(temp_folder, exist_ok=True)

        print(f"\n[{idx}/{len(videos)}] {os.path.basename(src)}")
        t0 = time.time()
        last_pct = {"v": -10}

        def on_log(msg: str) -> None:
            print(f"    · {msg}")

        def on_progress(pct: float, label: str = "") -> None:
            p = int(pct * 100)
            if p - last_pct["v"] >= 10:  # throttle: cada ~10%
                last_pct["v"] = p
                print(f"    [{p:3d}%] {label}")

        try:
            result = run_editor_auto_pipeline(
                user_id=user_id,
                input_video_path=src,
                job_id=job_id,
                temp_folder=temp_folder,
                on_log=on_log,
                on_progress=on_progress,
                source_filename=os.path.basename(src),
                output_override=out_path,
            )
            dt = time.time() - t0
            print(f"    ✅ {os.path.basename(result)}  ({dt:.0f}s)")
            ok.append(result)
        except Exception as e:  # noqa: BLE001 — una muestra que falla no para el lote
            print(f"    ❌ FALLÓ: {type(e).__name__}: {e}")
            fail.append((os.path.basename(src), f"{type(e).__name__}: {e}"))

    print("\n" + "=" * 70)
    print(f"RESUMEN: {len(ok)} ok · {len(fail)} fallidas")
    if ok:
        print(f"Muestras en: {out_dir}")
    for name, err in fail:
        print(f"  ❌ {name}: {err}")
    return 0 if not fail else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Genera muestras de edición por lote (captación Nebulabs Media).",
    )
    ap.add_argument("--list", action="store_true",
                    help="Lista los estilos (EditorUser) configurados y sale.")
    ap.add_argument("--user-id", help="ID del EditorUser cuyo flujo se aplica.")
    ap.add_argument("--in", dest="in_dir", default="./muestras_in",
                    help="Carpeta con los vídeos de entrada (default ./muestras_in).")
    ap.add_argument("--out", dest="out_dir", default="./muestras_out",
                    help="Carpeta de salida local (default ./muestras_out).")
    args = ap.parse_args()

    if args.list or not args.user_id:
        if not args.user_id and not args.list:
            print("Falta --user-id. Estilos disponibles:\n")
        return _list_styles()
    return _run_batch(args.user_id, args.in_dir, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
