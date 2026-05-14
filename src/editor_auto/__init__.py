"""Programa 3 — Editor Auto.

Editor de video modular: cada usuario configura un flujo (puzzle) con
herramientas componibles (subtítulos automáticos, cortador de silencios,
etc.). Al generar, el orchestrator reordena las herramientas por
`position_weight` (regla fija) y las ejecuta secuencialmente sobre el
video input que el usuario sube manualmente.

Estructura:
    config.py             — paths, redis_prefix, env vars
    models/               — EditorUser + ToolStep + JobConfig
    repos/                — Redis CRUD (prefijo `editor_auto:`)
    tools/                — herramientas plugin (base + registry + impls)
    services/             — flow_orchestrator (reorden + ejecución)
    pipeline/             — entry point para el runner
    api/                  — clientes externos (OpenAI dedicado)
    prompts/              — system prompts en .md
"""
