## 👤 Tareas Humanas

- [ ] **PENDIENTE · Editor Auto email avisos**: generar *contraseña de aplicación* en `nebulabsaimedia@gmail.com` (Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de aplicación → "Correo") y añadir al `.env` del server: `EDITOR_SMTP_USER=nebulabsaimedia@gmail.com` + `EDITOR_SMTP_APP_PASSWORD=<16 chars>` → recrear contenedor `api`. Hasta entonces, el botón "Marcar día listo" solo comparte la carpeta de salida (sin email). El código ya está listo (`src/editor_auto/services/email_notify.py`).
- [ ] **Editor Auto planes baratos** (cuando se asignen): meter al seeder Esencial 5 (249€/+fotos 289€) y Plus 10 (349€/+fotos 399€). Por ahora la config (delay + máx/día) se hace por usuario a mano.
- [ ] Probar generación async de presets en local (`/tiktok-shop/products/<id>` → tab Presets → "Regenerar todos") y verificar: barra progreso, cambio de tab sin perder estado, hard refresh recupera, toast final.
- [ ] Si OK → commit + push los cambios pendientes de la sesión (ver `SESSION_STATE.md` "Próximos pasos")
- [ ] Tras push → SSH al VPS y disparar `deploy_safe.sh` para aplicar
- [ ] Probar el flujo end-to-end del refactor TikTok Shop: crear producto desde URL → fotos → análisis → presets → /generate con bulk + smart variants

## 🤖 Cola del Agente

## ✅ Done

- [2026-05-18] Nicho 4 Construcción POV completo: JobMode + runner + pipeline (Gemini video → MiniMax → anti-copy + subs karaoke) + endpoints `/construccion-pov/enqueue` y `/voices/clone|sample|delete` + sidebar nav + página `/creator-reward/construccion-pov` + hub `/creator-reward/tools/voices` + 40 presets EN MiniMax.
