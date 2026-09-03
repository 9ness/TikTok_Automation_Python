# Acceso al VPS — runbook rápido

Notas de acceso al servidor Hetzner para tareas comunes (editar `.env`,
revisar logs, reiniciar servicios). Para el setup inicial completo ver
[`deploy/README.md`](README.md).

---

## Datos del servidor

| Campo | Valor |
|---|---|
| Proveedor | Hetzner Cloud (Console: `nebulabs-vps`, project `NeBulabs-AI`) |
| Tipo | CX33 — 4 vCPU, 8 GB RAM, 80 GB disco |
| IP pública | `62.238.19.31` |
| Región | Helsinki (eu-central) |
| Usuario root | `root` (acceso por SSH key) |
| Usuario app | `nebulabsai` (home: `/home/nebulabsai`) |
| Repo en servidor | `/home/nebulabsai/TikTok_Automation_Python/` |

---

## Conectar por SSH (PowerShell / Terminal)

```powershell
ssh root@62.238.19.31
```

Entras directo si tienes la clave SSH configurada localmente. Si te
pide password es la del servidor (Hetzner Console → Reset root password
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
curl -s http://62.238.19.31:9000/version

# 2. Contenedores vivos (API_KEY = la del .env)
curl -s http://62.238.19.31:9000/admin/docker/ps -H "X-API-Key: $API_KEY"
curl -s http://62.238.19.31:9000/admin/system   -H "X-API-Key: $API_KEY"

# 3. ¿Resuelve el nombre en DNS públicos? (si aquí SÍ, es el cliente)
dig +short @1.1.1.1 tiktok-factory.tailbff00e.ts.net

# 4. ¿Sirve por la ruta PÚBLICA? Ojo: desde un equipo del tailnet, el nombre
#    resuelve por dentro y un 200 NO prueba nada. Hay que forzar la IP del
#    ingress de Tailscale (las del paso 3):
curl -so /dev/null -w '%{http_code}\n' \
  --resolve tiktok-factory.tailbff00e.ts.net:443:185.40.234.55 \
  https://tiktok-factory.tailbff00e.ts.net/
```

**Plan B inmediato para el operador**: `http://62.238.19.31` sirve la app sin
DNS ni Tailscale (Caddy escucha en el 80 con `DOMAIN` vacío). Es HTTP, así que
solo para salir del paso.

**Arreglo definitivo pendiente**: un subdominio propio (tienen
`nebulabsmedia.com`) con un registro A a `62.238.19.31` y ese nombre añadido al
`Caddyfile` — Caddy saca el certificado solo y la app deja de depender de
Tailscale. Falta que el operador cree el DNS.

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
