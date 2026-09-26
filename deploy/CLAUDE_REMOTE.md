# Claude Code en el VPS — quitarlo y volver a ponerlo

Claude Code corre en el VPS para usarlo desde el móvil con el PC apagado:
Remote Control por proyecto + el chat web del menú «Claude» de la app. Todo lo
necesario para reinstalarlo está en el repo (esta carpeta `deploy/`). Lo único
que no se puede guardar es el **login**: hay que hacerlo con la cuenta que tenga
plan de Claude (Pro/Max).

## Qué hay instalado (sep 2026)

| Pieza | Dónde | Espacio |
|---|---|---|
| CLI de Claude Code | `~/.local/share/claude` (+ enlace `~/.local/bin/claude`) | ~0,9 GB |
| Chats, login y ajustes | `~/.claude/` y `~/.claude.json` | ~0,9 GB |
| Repos clonados para los agentes | `~/proyectos/*` (15 repos de github.com/9ness) | ~13 GB |
| Backend del chat web | `~/claude_chat/app.py` (copia en `deploy/claude_chat/`) + venv `~/.claude-sdk-test` | ~0,35 GB |
| Servicios systemd | `claude-remote@<repo>`, `claude-chat`, `claude-save-sessions` (+ timer), `claude-restore-sessions` | — |
| Cron (usuario `nebulabsai`) | `0 5 * * * ~/pull_proyectos.sh` y `0 4 * * * ~/backup_chats.sh` | — |
| Copia de los chats | `~/gdrive/CLAUDE_CHATS_BACKUP/chats_AAAA-MM-DD.tar.gz` (Drive, últimos 7) | en el Drive |

La app de TikTok NO depende de nada de esto para funcionar. Solo dejan de ir el
menú «Claude» de la web y los botones de «Claude Remoto» en Settings › Deploy.
El MCP de agentes (`src/agente_mcp/`) es otra cosa y sigue funcionando.

## Quitarlo (libera ~15 GB)

```bash
# 1. Última copia de los chats al Drive (por si se quieren recuperar)
sudo -u nebulabsai ~/backup_chats.sh

# 2. Parar y desactivar servicios (si se dejan, ciclan fallando sin login)
sudo systemctl disable --now "claude-remote@*" claude-remote claude-chat \
  claude-save-sessions.timer claude-save-sessions claude-restore-sessions
sudo -u nebulabsai tmux ls 2>/dev/null | grep -o '^rc_[^:]*' | xargs -r -n1 sudo -u nebulabsai tmux kill-session -t

# 3. Quitar el cron de pull y backup (deja el de nicho_pov_bof)
sudo -u nebulabsai crontab -l | grep -v -e pull_proyectos -e backup_chats | sudo -u nebulabsai crontab -

# 4. Borrar
cd /home/nebulabsai
rm -rf proyectos .claude .claude.json .local/share/claude .local/bin/claude .claude-sdk-test claude_chat
```

NO tocar `~/TikTok_Automation_Python` (la copia de producción que usa Docker) ni
`~/gdrive` (es el Drive montado, no ocupa disco).

## Volver a ponerlo (~30 min)

Como usuario `nebulabsai` salvo donde pone `sudo`.

1. **CLI**: `curl -fsSL https://claude.ai/install.sh | bash` (queda en
   `~/.local/bin/claude`). Node 20 y `gh` ya están instalados.
2. **Sin auto-update** (cada update resetea los flags de abajo y rompe los
   servicios): `export DISABLE_AUTOUPDATER=1` en `~/.bashrc` y `~/.profile`, y
   `"autoUpdates": false` en `~/.claude.json`.
3. **Login** (necesita a la persona: nunca meter credenciales por ella):
   `tmux new -s login -x 400 -y 50 claude` → `/login` → opción 1 (suscripción)
   → abrir la URL en el navegador, autorizar y pegar el código en tmux (a veces
   hace falta un segundo Enter). Para sacar la URL desde otra terminal:
   `tmux capture-pane -p -J -t login | grep -oE "https://claude\.(ai|com)/[^ ]+"`.
   En esa misma sesión, responder «y» UNA vez a «Enable Remote Control?».
4. **Repos**: `mkdir ~/proyectos && cd ~/proyectos` y
   `gh repo list 9ness --limit 50 --json name -q '.[].name' | xargs -n1 gh repo clone`
   (o solo los que se vayan a usar). Restaurar `~/pull_proyectos.sh` (ver abajo).
5. **Flags para que arranque sin preguntar** — en `~/.claude.json`:
   `hasCompletedOnboarding: true`, `remoteDialogSeen: true` y, en `projects`,
   una entrada `{"hasTrustDialogAccepted": true}` para `/home/nebulabsai/proyectos`
   y para CADA `~/proyectos/<repo>` (hay que CREARLAS; si falta una, su
   servicio cicla para siempre con «Workspace not trusted»).
6. **Chats antiguos** (opcional): `tar xzf ~/gdrive/CLAUDE_CHATS_BACKUP/chats_<fecha>.tar.gz -C ~/.claude`.
7. **Chat web**:
   ```bash
   mkdir ~/claude_chat && cp ~/TikTok_Automation_Python/deploy/claude_chat/app.py ~/claude_chat/
   python3 -m venv ~/.claude-sdk-test
   ~/.claude-sdk-test/bin/pip install -r ~/TikTok_Automation_Python/deploy/claude_chat/requirements.txt
   ```
   `app.py` lee `API_KEY` de `~/TikTok_Automation_Python/.env` (la de la app), no hay que configurar nada. El
   firewall ya deja `172.18.0.0/16 → 8765` y Caddy ya tiene el bloque
   `/claude-chat/*`.
8. **Servicios** (`sudo`):
   ```bash
   cd /home/nebulabsai/TikTok_Automation_Python/deploy/systemd
   cp -r claude-remote@.service claude-remote@.service.d claude-chat.service claude-chat.service.d \
         claude-save-sessions.service claude-save-sessions.timer claude-restore-sessions.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now claude-chat claude-save-sessions.timer claude-restore-sessions
   for r in /home/nebulabsai/proyectos/*/; do systemctl enable --now "claude-remote@$(basename $r)"; done
   ```
9. **Cron**: volver a poner las dos líneas de la tabla de arriba.
   `pull_proyectos.sh` hace `git pull --ff-only` en cada repo de `~/proyectos`.
   `backup_chats.sh` hace `tar czf ~/gdrive/CLAUDE_CHATS_BACKUP/chats_$(date +%F).tar.gz -C ~/.claude projects`
   y deja los 7 últimos.
10. **Comprobar**: `systemctl list-units --all | grep claude-remote@`. Ninguno
    debe salir «activating auto-restart». Los proyectos tienen que aparecer en
    la app de Claude › Code.

Si tras un re-login algo sigue diciendo «Not logged in», hay que reiniciar
`claude-chat` y todos los `claude-remote@*`, porque guardan el token en memoria.
Más gotchas en `learnings.md` (buscar «Remote Control»).
