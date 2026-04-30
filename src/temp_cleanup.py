"""Auto-limpieza de la carpeta temp_work.

Borra archivos cuya última modificación supera `max_age_days` y limpia
carpetas vacías. Throttling vía marker file para evitar repeticiones en
los reruns de Streamlit.
"""
import time
from pathlib import Path

CLEANUP_MARKER = ".last_cleanup"
PROTECTED_NAMES = {CLEANUP_MARKER, ".gitkeep", ".gitignore"}


def cleanup_temp_files(temp_dir, max_age_days=3, throttle_hours=12, force=False):
    """Borra archivos en `temp_dir` con mtime mayor que `max_age_days`.

    Throttling: si la limpieza se hizo hace menos de `throttle_hours` no
    vuelve a ejecutarse (evita correr en cada rerun de Streamlit). Pasa
    `force=True` para saltar el throttle.

    Returns: (n_archivos_borrados, bytes_liberados).
    """
    temp_path = Path(temp_dir)
    if not temp_path.is_dir():
        return (0, 0)

    marker = temp_path / CLEANUP_MARKER
    now = time.time()

    if not force and marker.exists():
        if (now - marker.stat().st_mtime) < (throttle_hours * 3600):
            return (0, 0)

    cutoff = now - (max_age_days * 86400)
    deleted = 0
    freed = 0

    for entry in temp_path.rglob("*"):
        if not entry.is_file() or entry.name in PROTECTED_NAMES:
            continue
        try:
            stat = entry.stat()
            if stat.st_mtime < cutoff:
                size = stat.st_size
                entry.unlink()
                deleted += 1
                freed += size
        except OSError:
            pass

    # Limpiar carpetas vacías de abajo hacia arriba
    for entry in sorted(temp_path.rglob("*"), key=lambda p: -len(str(p))):
        if entry.is_dir():
            try:
                if not any(entry.iterdir()):
                    entry.rmdir()
            except OSError:
                pass

    try:
        marker.touch()
    except OSError:
        pass

    return (deleted, freed)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Limpieza de temp_work")
    parser.add_argument("--dir", default="./temp_work", help="Carpeta a limpiar")
    parser.add_argument("--days", type=int, default=3, help="Edad máxima en días")
    parser.add_argument("--force", action="store_true", help="Ignora el throttle")
    args = parser.parse_args()

    n, freed = cleanup_temp_files(args.dir, max_age_days=args.days, force=args.force)
    print(f"[temp_cleanup] {n} archivos borrados / {freed / 1024 / 1024:.1f} MB liberados")
