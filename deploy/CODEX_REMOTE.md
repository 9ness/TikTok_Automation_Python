# Codex en el VPS — qué hay, cómo quitarlo y cómo reinstalarlo

Codex (el agente de OpenAI, con la cuenta de ChatGPT) corre en el VPS para
usarlo desde la app de ChatGPT/Codex en el móvil con el PC apagado, sobre los
repos de `~/proyectos` (los mismos que usa Claude, ver `CLAUDE_REMOTE.md`).
Lo único que no se puede guardar es el **login** de la cuenta de ChatGPT.

## Qué hay instalado (sep 2026)

| Pieza | Dónde | Espacio |
|---|---|---|
| CLI standalone | `~/.codex/packages/standalone/` (versión en `current`, las viejas en `releases/`) + enlaces `~/.local/bin/codex` y `/usr/local/bin/codex` | ~1,8 GB (unos 370 MB por versión) |
| Login | `~/.codex/auth.json` | — |
| Ajustes | `~/.codex/config.toml` (modelo, esfuerzo, plugins) | — |
| Hilos, memoria y logs | `~/.codex/sessions`, `*.sqlite` | ~120 MB |
| Servicio | `codex-remote.service` (copia en `deploy/systemd/`) | — |
| Repos | `~/proyectos/*`, compartidos con Claude | ~13 GB |

## Liberar espacio SIN quitarlo

El instalador guarda cada versión que se baja (el auto-update las acumula). Se
pueden borrar todas menos la actual:

```bash
cd ~/.codex/packages/standalone/releases
actual=$(cat ../auto-update-version)
ls | grep -v "^$actual$" | xargs -r rm -rf
```

## Quitarlo

```bash
sudo systemctl disable --now codex-remote
codex remote-control stop 2>/dev/null
rm -rf ~/.codex ~/.local/bin/codex && sudo rm -f /usr/local/bin/codex
```

`~/proyectos` NO se borra aquí si Claude sigue instalado: los repos son de los
dos. Si se quitan los dos, ver `CLAUDE_REMOTE.md › Quitarlo`.

## Volver a ponerlo

1. **CLI**: `curl -fsSL https://chatgpt.com/codex/install.sh | sh`. TIENE que ser
   el instalador standalone: el paquete npm `@openai/codex` no sirve para el
   daemon remoto. Y no hagas `npm uninstall -g @openai/codex` después, porque
   se lleva por delante el enlace `~/.local/bin/codex`. Enlace global opcional:
   `sudo ln -sf ~/.codex/packages/standalone/current/bin/codex /usr/local/bin/codex`.
2. **Login** (necesita a la persona; nunca meter credenciales por ella):
   `codex login --device-auth`. Abre la URL en el navegador, entra con la
   cuenta de ChatGPT y escribe el código que muestra la terminal. Queda en
   `~/.codex/auth.json`.
3. **Ajustes**: `~/.codex/config.toml` con el modelo y el esfuerzo que se
   quieran (en sep 2026 estaba `model = "gpt-6-sol"`,
   `model_reasoning_effort = "medium"`).
4. **Repos**: si no están, clonarlos como en `CLAUDE_REMOTE.md` (paso 4).
5. **Servicio** (`sudo`):
   ```bash
   cp /home/nebulabsai/TikTok_Automation_Python/deploy/systemd/codex-remote.service /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now codex-remote
   ```
   Es `oneshot` + `RemainAfterExit` + `KillMode=process` porque
   `codex remote-control start` es un cliente que arranca el daemon y sale.
   `start` es idempotente, así que reiniciar no duplica procesos.
6. **Proyectos en el móvil**: el selector «Elegir proyecto» NO lista carpetas
   del disco. Lista los *projects* del app-server, y solo los que ya tienen un
   hilo con un turno ejecutado. Para dar de alta un repo, lo más sencillo es
   abrir un hilo en él una vez:
   `cd ~/proyectos/<repo> && codex exec "di hola"`.
   Si con eso no aparece, hay que hacerlo por el socket de control del
   app-server: WebSocket sobre el socket UNIX (`codex app-server proxy` solo
   relaya bytes, el handshake WS lo hace el cliente), con
   `initialize{capabilities.experimentalApi:true}` → `project/create` →
   `thread/start{projectId, cwd}` → `turn/start`.
7. **Comprobar**: `systemctl status codex-remote` debe estar `active (exited)`,
   y los proyectos deben aparecer en la app de Codex.
