# Acceso al VPS — runbook rápido

> Migrado de Hetzner a **Contabo** el 4-nov-2026 (el servidor de Hetzner `nebulabs-vps` está borrado).

Notas de acceso al VPS grande (`vps-trabajo`) para tareas comunes (editar `.env`,
revisar logs, reiniciar servicios). Para el setup inicial completo ver
[`deploy/README.md`](README.md).

---

## Datos del servidor

| Campo | Valor |
|---|---|
| Proveedor | Contabo Cloud VPS (`vps-trabajo`) |
| Tipo | 8 vCPU, 23 GB RAM, 145 GB disco (+8 GB swap) |
| IP pública | `13.140.211.41` · Tailscale `100.96.125.108` |
| VPS de las webs | `vps-webs`: `13.140.211.14` · Tailscale `100.83.196.101` (Caddy público, panel, links, Mora, tiktok-web) |
| Usuario root | `root` (acceso por SSH key) |
| Usuario app | `nebulabsai` (home: `/home/nebulabsai`) |
| Repo en servidor | `/home/nebulabsai/TikTok_Automation_Python/` |

---

## Datos grandes (`/mnt/HC_Volume_106974679`)

En Hetzner era un Volume aparte; en Contabo es una **carpeta del disco principal** con la misma ruta
(se conservó al migrar para no tocar `.env` ni servicios). Ya no hay volumen que ampliar: el límite es
el disco de 145 GB.

| Carpeta del volumen | Qué es | Quién la usa |
|---|---|---|
| `api_temp/` | `/app/temp_work` del container `api`: **la cola** (`queue_state.json`), subidas, vídeos intermedios | `docker-compose.yml` vía `API_TEMP_PATH` en `.env` |
| `rclone-cache/` | caché VFS del mount del Drive (tope 15 GB / 72 h) — incluye las subidas a Drive PENDIENTES | `gdrive-mount.service` (`--cache-dir`) |

Reglas:
- Lo que crece (temporales, cachés, salidas) va al volumen; el sistema, Docker
  (imágenes) y los repos se quedan en el disco principal.
- Cambiar `API_TEMP_PATH` o `--cache-dir` es mover datos VIVOS: con la cola
  parada (0 jobs `running`), parar el servicio, copiar con `rsync -aHAX`,
  arrancar. Con una carpeta vacía se pierde la cola o las subidas pendientes.
- Parar `gdrive-mount` con la API arrancada deja el mount COLGADO
  ("Transport endpoint is not connected": el container lo tiene en uso y
  `fusermount3 -u` falla con "busy"; el `start` siguiente falla el
  `AssertPathIsDirectory`). Salida: `fusermount3 -uz ~/gdrive`, `systemctl
  reset-failed gdrive-mount && systemctl start gdrive-mount` y RECREAR el
  container api (`docker compose up -d --no-deps --force-recreate api`, con 0
  jobs running): el suyo se queda con el mount muerto aunque el host ya vea
  el Drive. Pasó el 28-sep-2026 al mover la caché.
- Sigue valiendo lo de siempre: NUNCA `docker compose down -v`.
- Espacio: `df -h / /mnt/HC_Volume_106974679`.

---

## Conectar por SSH (PowerShell / Terminal)

```powershell
ssh root@13.140.211.41
```

Entras directo si tienes la clave SSH configurada localmente. Si te
pide password es la del servidor (panel de Contabo → reset de contraseña
si no la recuerdas).

---

## Editar el `.env`

El `.env` vive en el home del usuario `nebulabsai`, NO de root.
Editable como root sin cambiar de usuario.

```bash
nano /home/nebulabsai/TikTok_Automation_Python/.env
```

Atajos `nano`:
- Edita con flechas + escritura
- `Ctrl+O` → `Enter` para **guardar**
- `Ctrl+X` para **salir**

> El `.env` está en `.gitignore` → los `git pull` del autodeploy NUNCA
> lo sobreescriben. Solo se edita manualmente cuando hay claves nuevas.

### Verificar qué claves están definidas (sin exponer valores)

```bash
grep -E "^(ATLASCLOUD|GOOGLE_GEMINI|TIKTOK_SHOP|MINIMAX|OPENAI|UPSTASH)" \
  /home/nebulabsai/TikTok_Automation_Python/.env \
  | sed 's/=.*/=<SET>/'
```

---

## Reiniciar la app tras cambios manuales

Cuando editas el `.env` (o cualquier cosa fuera de `git pull`):

```bash
# Listar servicios para encontrar el nombre exacto
systemctl list-units --type=service | grep -iE "tiktok|streamlit|nebula"

# Reiniciar (sustituye <nombre> por el que aparezca, ej. tiktok-app.service)
systemctl restart <nombre>

# Verificar que arrancó OK
systemctl status <nombre>
```

---

## "No me va la web ni la app" — comprobar ANTES de tocar nada

Pasó el 2-3 de septiembre de 2026: el móvil daba `ERR_NAME_NOT_RESOLVED` con
`https://tiktok-factory.tailbff00e.ts.net/` y el servidor estaba perfecto. Se
arregló solo al caducar la caché de DNS del teléfono — **no se tocó nada**.

La app se sirve por **Tailscale Funnel**, así que ese nombre lo publica
Tailscale: si el móvil no lo resuelve (Tailscale a medias en el propio
teléfono, "DNS privado" de Android apuntando a un servidor que no responde,
caché envenenada del router) no hay web, aunque el VPS esté impecable.

Estas cuatro comprobaciones se hacen desde cualquier sitio, **sin SSH**, y
dicen en un minuto si el problema es del servidor o del cliente:

```bash
# 1. Qué commit corre y si el último deploy acabó bien (sin auth)
curl -s http://13.140.211.41:9000/version

# 2. Contenedores vivos (API_KEY = la del .env)
curl -s http://13.140.211.41:9000/admin/docker/ps -H "X-API-Key: $API_KEY"
curl -s http://13.140.211.41:9000/admin/system   -H "X-API-Key: $API_KEY"

# 3. ¿Resuelve el nombre en DNS públicos? (si aquí SÍ, es el cliente)
dig +short @1.1.1.1 tiktok-factory.tailbff00e.ts.net

# 4. ¿Sirve por la ruta PÚBLICA? Ojo: desde un equipo del tailnet, el nombre
#    resuelve por dentro y un 200 NO prueba nada. Hay que forzar la IP del
#    ingress de Tailscale (las del paso 3):
curl -so /dev/null -w '%{http_code}\n' \
  --resolve tiktok-factory.tailbff00e.ts.net:443:185.40.234.55 \
  https://tiktok-factory.tailbff00e.ts.net/
```

**Plan B inmediato para el operador**: `https://13-140-211-14.sslip.io` (mismo Caddy del VPS de
las webs, sin depender del DNS del dominio).

El subdominio propio ya existe: `factory.nebulabsmedia.com` (registro A en Vercel → `13.140.211.14`).

## Las DOS puertas de entrada (y por qué hay dos)

El 4 de septiembre de 2026 el Tailscale Funnel dejó de publicar el nombre
`.ts.net` por segunda vez en dos días: el servidor perfecto y la web caída
para todo el mundo, móvil y PC. Desde entonces hay una puerta que no depende
de Tailscale:

| URL | Quién la sirve | Notas |
|---|---|---|
| **`https://factory.nebulabsmedia.com`** | Caddy del VPS pequeño (`13.140.211.14:443`) → API del grande por Tailscale (`100.96.125.108:8080`) | **La buena.** Dominio propio, certificado de Let's Encrypt, sin Tailscale de por medio. |
| `https://13-140-211-14.sslip.io` | Caddy, mismo sitio | Reserva por si el DNS del dominio falla. `sslip.io` resuelve `<ip-con-guiones>` a esa IP. |
| `http://13.140.211.14` | Caddy en `:80` | **Redirige** al dominio. Antes servía la app en claro a quien probara la IP. |
| `https://tiktok-factory.tailbff00e.ts.net:8443` | Tailscale Funnel → portero `:8090` | La vieja. Depende de que Tailscale publique el nombre — dejó de hacerlo el 4/9/2026. |

### Cuando el Funnel deja de resolver

Pasó el 3 y el 4 de septiembre de 2026. Síntoma: `tailscale serve status` dice
"Funnel on" y el servidor está perfecto, pero el nombre da NXDOMAIN **en el
DNS autoritativo de `ts.net`** (comprobado contra `ns1.dnsimple.com`), no solo
en el resolutor de turno. Eso NO se arregla desde la máquina: Tailscale ha
dejado de publicar el nombre.

Dónde mirar, en la consola de Tailscale:

- **DNS → HTTPS Certificates**: tiene que estar activado.
- **Access controls**: hace falta el atributo de Funnel para el nodo:
  `"nodeAttrs": [{"target": ["*"], "attr": ["funnel"]}]`.

Y después, en el servidor, el proxy correcto (a Caddy, NO a `127.0.0.1:443`,
que es un lazo y devuelve 502):

```bash
sudo tailscale funnel --bg --https=443 http://127.0.0.1:80
sudo tailscale serve status
```

`sslip.io` resuelve `<ip-con-guiones>.sslip.io` a esa IP, así que no hubo que
comprar dominio ni crear DNS. Cuando haya uno propio, se cambia esa línea del
`Caddyfile` por él y se crea el registro A.

Tres cosas viven FUERA del repo, en esta máquina, y hay que saberlas:

1. **`docker-compose.override.yml`** (root, no está en git): en el VPS grande Caddy solo publica el
   `:8080`, y una regla `DOCKER-USER` (también en `/etc/ufw/after.rules`) lo cierra a todo lo que no
   venga por `tailscale0`. Lo público lo sirve el Caddy del VPS pequeño (`/etc/caddy/Caddyfile`,
   `default_bind 13.140.211.14` para no chocar con tailscaled en el `:443`).
2. **`juegos-bridge.socket` / `.service`**: el portero del código
   (`juegos-server`) escucha solo en `127.0.0.1:8090` y desde el contenedor de
   Caddy no se alcanza. Este puente de systemd lo abre en `172.18.0.1:8091`.
3. **Regla ufw**: `allow from 172.18.0.0/16 to any port 8091` — sin ella, el
   contenedor no llega al puente y sale un 502.

Y DOS avisos sobre el `Caddyfile`, que se tapaban el uno al otro y costaron
una mañana:

1. **`docker compose up -d caddy` no aplica un cambio del fichero.** Como va
   montado, la definición del servicio no cambia y docker deja el contenedor
   como está — el deploy cantaba "✅ caddy reiniciado" con un contenedor de
   cinco semanas y la config vieja. Ahora `deploy_safe.sh` hace
   `caddy reload`, que además no corta conexiones.
2. **Un bind-mount de un FICHERO sigue el inodo, no la ruta.** `git pull` (o
   cualquier cosa que reescriba el fichero) crea un inodo nuevo y el
   contenedor se queda leyendo el viejo: `caddy reload` recarga… lo de antes.
   Cuando el cambio no aparezca, comprobarlo desde dentro:

   ```bash
   docker exec tiktok-caddy grep -c nebulabsmedia /etc/caddy/Caddyfile
   ```

   Si no cuadra con el fichero del host, hay que
   `docker compose up -d --force-recreate caddy`.

## Logs y debugging

```bash
# Logs en vivo del servicio principal
journalctl -u <nombre-servicio> -f

# Últimas 200 líneas
journalctl -u <nombre-servicio> -n 200

# Ver procesos Streamlit
ps aux | grep streamlit

# Disco / memoria
df -h
free -h
```

---

## Forzar pull manual del repo (si el autodeploy falla)

```bash
su - nebulabsai
cd ~/TikTok_Automation_Python
git pull
exit
systemctl restart <nombre-servicio>
```

---

## Comandos útiles para encontrar cosas

Si pierdes la pista de dónde están los archivos:

```bash
# Encontrar el .env
find / -name ".env" 2>/dev/null

# Encontrar la carpeta del repo
find / -type d -name "TikTok_Automation_Python" 2>/dev/null

# Ver qué hay en el home del usuario app
ls -la /home/nebulabsai/

# Ver el setup.sh original
cat /root/setup.sh
```

---

## Flujo normal de cambios (referencia)

1. **Cambios de código** → push a GitHub → autodeploy hace `git pull` +
   `systemctl restart` solo. Nada manual.
2. **Cambios en `.env`** → SSH al servidor → editar `.env` con `nano` →
   reiniciar el servicio manualmente.
3. **Cambios en `requirements.txt`** → autodeploy debería reinstalar
   deps (revisar `deploy/install_app.sh` / hooks). Si no lo hace,
   manualmente: `su - nebulabsai && cd ~/TikTok_Automation_Python &&
   source venv/bin/activate && pip install -r requirements.txt`.
