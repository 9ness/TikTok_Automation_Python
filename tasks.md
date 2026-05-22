## 👤 Tareas Humanas

- [ ] Probar generación async de presets en local (`/tiktok-shop/products/<id>` → tab Presets → "Regenerar todos") y verificar: barra progreso, cambio de tab sin perder estado, hard refresh recupera, toast final.
- [ ] Si OK → commit + push los cambios pendientes de la sesión (ver `SESSION_STATE.md` "Próximos pasos")
- [ ] Tras push → SSH al VPS y disparar `deploy_safe.sh` para aplicar
- [ ] Probar el flujo end-to-end del refactor TikTok Shop: crear producto desde URL → fotos → análisis → presets → /generate con bulk + smart variants

## 🤖 Cola del Agente

## ✅ Done

- [2026-05-18] Nicho 4 Construcción POV completo: JobMode + runner + pipeline (Gemini video → MiniMax → anti-copy + subs karaoke) + endpoints `/construccion-pov/enqueue` y `/voices/clone|sample|delete` + sidebar nav + página `/creator-reward/construccion-pov` + hub `/creator-reward/tools/voices` + 40 presets EN MiniMax.
