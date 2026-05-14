"""CRUD de usuarios del programa Editor Auto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_user
from src.api.exceptions import UserNotFoundError, ValidationError
from src.api.schemas.editor_auto import (
    EditorUserCreateRequest,
    EditorUserResponse,
    EditorUserUpdateRequest,
    ToolStepIn,
)
from src.editor_auto.config import (
    TOOL_EXCLUSIVE_GROUPS,
    ensure_user_folders,
    user_folder,
    user_output_folder,
)
from src.editor_auto.models import EditorUser, ToolStep
from src.editor_auto.repos import UserRepo
from src.editor_auto.tools import REGISTRY


router = APIRouter(
    prefix="/api/v1/editor-auto/users",
    tags=["editor-auto · users"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(u: EditorUser) -> EditorUserResponse:
    # Recalcula `drive_folder` y `output_folder` dinámicamente en cada GET
    # — así si la raíz cambia (env var nueva, autodetect mejorado), los
    # users existentes apuntan al sitio correcto SIN tener que migrar
    # nada en Redis. El campo `u.drive_folder` que viene de la BD se
    # mantiene como referencia histórica pero no se devuelve al cliente.
    return EditorUserResponse(
        id=u.id,
        name=u.name,
        display_name=u.display_name,
        description=u.description,
        tool_flow=[ToolStepIn(**s.model_dump()) for s in u.tool_flow],
        drive_folder=user_folder(u.name) if u.name else None,
        output_folder=user_output_folder(u.name) if u.name else None,
        deleted=u.deleted,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


def _validate_steps(steps: list[ToolStepIn]) -> list[ToolStep]:
    """Valida que cada step apunte a una herramienta registrada y
    convierte a `ToolStep` interno. Aplica también las reglas de
    exclusión mutua de `TOOL_EXCLUSIVE_GROUPS` (ej. silence_cutter vs
    silence_cutter_scripted no pueden coexistir habilitados en el mismo
    flujo — la 1ª mutila el input de la 2ª)."""
    out: list[ToolStep] = []
    for s in steps:
        if s.tool_id not in REGISTRY:
            raise ValidationError(
                f"Herramienta desconocida: '{s.tool_id}'",
                details={"valid_tool_ids": list(REGISTRY.keys())},
            )
        out.append(ToolStep(
            tool_id=s.tool_id, enabled=s.enabled, config=s.config or {},
        ))
    enabled_ids = {s.tool_id for s in out if s.enabled}
    for group in TOOL_EXCLUSIVE_GROUPS:
        clash = enabled_ids & group
        if len(clash) > 1:
            raise ValidationError(
                "Estas herramientas no son compatibles entre sí en el mismo "
                f"flujo: {sorted(clash)}. Deshabilita o elimina una.",
                details={
                    "conflicting_tool_ids": sorted(clash),
                    "exclusive_group": sorted(group),
                },
            )
    return out


@router.get("", response_model=list[EditorUserResponse])
def list_users(include_deleted: bool = False) -> list[EditorUserResponse]:
    repo = UserRepo()
    users = repo.list_all(include_deleted=include_deleted)
    return [_to_response(u) for u in users]


@router.get("/{user_id}", response_model=EditorUserResponse)
def get_user(user_id: str) -> EditorUserResponse:
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
    return _to_response(u)


@router.post("", response_model=EditorUserResponse,
             status_code=status.HTTP_201_CREATED)
def create_user(payload: EditorUserCreateRequest) -> EditorUserResponse:
    repo = UserRepo()
    if repo.get_by_name(payload.name) is not None:
        raise ValidationError(
            f"Ya existe un usuario con el nombre '{payload.name}'",
            details={"name": payload.name},
        )
    steps = _validate_steps(payload.tool_flow)
    # Crear carpetas en Drive sincronizado ANTES de guardar en Redis, así
    # `resolve_editor_root` tiene chance de auto-detectar el padre y crear
    # TIKTOK_EDITOR como hermana de TIKTOK_CR/TIKTOK_SHOP. Si Drive no
    # está accesible cae al fallback local (visible en el path devuelto).
    try:
        ensure_user_folders(payload.name)
    except OSError as e:
        print(f"[editor_auto.users] ensure_user_folders falló: {e}")
    user = EditorUser(
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        tool_flow=steps,
        drive_folder=user_folder(payload.name),
    )
    repo.save(user)
    return _to_response(user)


@router.patch("/{user_id}", response_model=EditorUserResponse)
def update_user(
    user_id: str, payload: EditorUserUpdateRequest,
) -> EditorUserResponse:
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
    if payload.display_name is not None:
        u.display_name = payload.display_name
    if payload.description is not None:
        u.description = payload.description
    if payload.tool_flow is not None:
        u.tool_flow = _validate_steps(payload.tool_flow)
    # Asegurar carpetas en Drive — idempotente. Cubre el caso de users
    # creados antes de que `resolve_editor_root` supiera autodetectar el
    # padre del Drive (entonces cayeron al fallback local).
    try:
        ensure_user_folders(u.name)
    except OSError as e:
        print(f"[editor_auto.users] ensure_user_folders falló en PATCH: {e}")
    repo.save(u)
    return _to_response(u)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, hard: bool = False) -> None:
    repo = UserRepo()
    ok = repo.delete(user_id, hard=hard)
    if not ok:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
