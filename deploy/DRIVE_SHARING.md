# Google Drive Sharing — Editor Auto

Compartir las carpetas `entrada/` y `salida/` de cada usuario con un
gmail concreto desde la UI del panel.

## Arquitectura

```
Frontend Settings → UserFoldersPanel → "Personas con acceso"
   │ POST /api/v1/editor-auto/users/{id}/shares  body: {email, folders}
   ▼
FastAPI → src/api/routers/editor_auto/sharing.py
   │ drive_sharing.share_folders(username, email, folders)
   ▼
src/editor_auto/services/drive_sharing.py
   │ google-api-python-client + Service Account JSON
   ▼
Google Drive API (drive.permissions.create)
```

## Setup one-time

### 1. GCP — crear Service Account

Logueate como `nebulabsaimedia@gmail.com` (cuenta compartida del equipo)
en https://console.cloud.google.com.

1. **New Project** → nombre `nebulabs-editor`
2. Buscador → **Google Drive API** → ENABLE
3. **IAM & Admin → Service Accounts → + CREATE**
   - Name: `nebulabs-editor`
   - Skip roles (no necesita roles GCP)
   - CREATE
4. Click en el SA recién creado → **KEYS → ADD KEY → Create new key → JSON**
   - Descarga el archivo
5. Copia el **email del SA** (formato `nebulabs-editor@nebulabs-editor-XXXXX.iam.gserviceaccount.com`)

### 2. Drive — dar acceso al SA

En drive.google.com (con `ness4b@gmail.com` o nebulabsaimedia):
1. Carpeta `TIKTOK_EDITOR/` → click derecho → **Compartir**
2. Pega el email del SA → rol **Editor** → Enviar
3. Confirma "compartir con usuario externo" si avisa

### 3. Server — subir JSON

Por SSH al server:
```bash
cd /home/nebulabsai/TikTok_Automation_Python
mkdir -p secrets
chmod 700 secrets
nano secrets/google-sa.json
```
Pega el contenido del JSON descargado → Ctrl+O → Enter → Ctrl+X.
```bash
chmod 600 secrets/google-sa.json
```

### 4. Aplicar cambios — desde el panel Deploy

Tras hacer `git push`, ve a **Settings → Deploy** → click **"Aplicar N
commits"**. El smart deploy detecta cambios en `src/editor_auto/`,
`docker-compose.yml` y `requirements.txt`, rebuildea api + recrea
container con el bind-mount `secrets/`.

Verifica desde la UI: entra a un usuario → tab Carpetas → al final
verás "Personas con acceso" con el form de email.

## Operación normal

1. En **Editor Auto → Usuarios → @user → Carpetas → Personas con
   acceso**: input email + botón Compartir
2. La persona recibe email de Drive con link a `entrada/` y `salida/`
3. La persona puede SUBIR videos a `entrada/` (es Reader, no Writer
   por defecto — para subir tendrá que ser invitada como Editor).
   Si quieres dar permiso de subida cambia `role: "writer"` en la API
   o añade selector en la UI.

## Revocar acceso

Al lado de cada email en la lista → ✕ → confirma. Drive revoca el
permission en `entrada/` y `salida/` al mismo tiempo.

## Diagnóstico

- **"Sharing de Drive no configurado"** en la UI: falta el JSON en
  `/app/secrets/google-sa.json` dentro del container. Comprueba que
  `secrets/google-sa.json` existe en el host y que el bind-mount está
  en `docker-compose.yml`.
- **"No encuentro la carpeta TIKTOK_EDITOR"**: el SA no tiene acceso a
  esa carpeta. Re-comparte desde Drive como Editor.
- **"No encuentro la carpeta del usuario"**: rclone aún no sincronizó.
  Espera 1-2 min o haz `ls` por SSH para forzar refresh de rclone.

## Seguridad

- `secrets/` está en `.gitignore` — el JSON nunca se sube al repo.
- El bind-mount es **read-only** (`:ro`) — el container no puede
  modificar el archivo.
- El SA tiene acceso SOLO a `TIKTOK_EDITOR/` (lo que explícitamente
  compartiste), nada más en el Drive del owner.
- El scope `https://www.googleapis.com/auth/drive` da acceso a
  archivos compartidos con el SA, no a todo el Drive del owner.
