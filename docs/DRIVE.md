# Google Drive: dónde va cada cosa (Nebulabs)

> Fuente de verdad para personas y agentes. Reorganización del 4-5/11/2026.
> Si cambias una carpeta de sitio, actualiza este fichero, `src/rutas_drive.py` (alias) y
> la sección «Dónde va cada cosa en el Drive» de `~/.claude/CLAUDE.md`.

## Cómo se ve el Drive

- **vps-trabajo (host):** `~/gdrive` (rclone FUSE, servicio `gdrive-mount`). Remoto rclone: `gdrive:`.
- **Contenedor `tiktok-api`:** `/mnt/drive`.
- Lo pesado se mueve **dentro del Drive** (`rclone moveto/copy gdrive:A gdrive:B`), nunca
  descargando por el VPS.

## Árbol

`Nebulabs/` es la carpeta de TODOS los proyectos. Es **privada** (solo Néstor). Dentro,
`TikTok/` es la antigua `NEBULABS_AUTOMATED_TIKTOK`, movida con su mismo ID: sigue
**compartida** con bugalleitor y las cuentas de servicio `Nebulabs` y `nebulabs-editor`.
Lo que se meta en `TikTok/` lo ven ellos; lo que vaya fuera, no.

```
Nebulabs/                                   (privada)
├── TikTok/                                 (compartida · antes NEBULABS_AUTOMATED_TIKTOK)
│   ├── TikTok Shop/                        Programa 4 «Tiktok Shop AI Pro» (antes TIKTOK_SHOP_AI_PRO)
│   │   ├── Nicho_*/ Replicar_*/ Top_Vendidos/ VIRALIZACION/ Cuenta_Piloto/ Formato_Duelo/…
│   │   ├── Replicar_Carrusel/<usuario>/<id>/   carruseles (Mis tandas › Fotos)
│   │   ├── Replicar_Viral/<usuario>/           réplicas en vídeo (nes_bugallo = cuenta árabe)
│   │   ├── _raiz_antigua/                  la TIKTOK_SHOP_AI_PRO que estaba suelta en la raíz (Compartir, Pruebas_Seedance, Canary…)
│   │   ├── Multiplataforma/<cuenta>/{viralizacion,producto,fotos}/   (Meta: viva_shop, viva_salud, ama_shop…)
│   │   ├── _agente/<usuario>/              bandejas de los agentes (MCP)
│   │   ├── _clases/ _apelaciones/ Investigacion/ _pruebas_*/
│   │   └── _curso/                         material del curso: Skool, copias y paquete de Productos España
│   ├── Creator Reward/                     (antes TIKTOK_CR · CR_DRIVE_DIR)
│   │   ├── TIKTOK_ASSETS/                  bibliotecas de Presidentes / Pronósticos (TIKTOK_ROOT_PATH)
│   │   └── FrutiNovelas/                   FrutiDramas y FrutiChismes (PARA_SUBIR/<cuenta>/<día>/, series, perfiles)
│   ├── TIKTOK_EDITOR/                      Editor Auto, por clientes (Usuarios/<cliente>/…) · nombre SIN cambiar, ver nota
│   ├── TIKTOK_SHOP/                        Programa 2, afiliado antiguo con Seedance · nombre SIN cambiar
│   └── (APKs, Dots Grupo, NINTENDO_PS4, VIDEOS_TERMINADOS, _archivo_vps… pendientes de decidir)
├── Master Picks/
│   ├── TikTok/                             antes MASTERPICKS_TIKTOK (C1/C2_LISTO_PARA_SUBIR/<fecha>/)
│   └── Comparativa/                        antes MASTERPICKS_COMPARATIVA (Excel de modelos)
├── Mora TV/
│   ├── APK/                                antes MiPlayer_APK
│   ├── Maquetas/                           antes MoraTV
│   └── copias/                             copias viejas de la base (las nuevas viven en vps-webs ~/copias/mora-tv)
├── Fit9ness/
│   ├── whoop/                              antes fit9ness-whoop
│   └── Health Motion/                      antes Health_Motion (propuesta al gimnasio)
├── Asistentes/                             antes _consultas (Ana/, Nestor/: carpetas de Dot)
├── Agentes/
│   └── backups_chats/                      antes CLAUDE_CHATS_BACKUP (tar.gz diarios de ~/.claude/projects)
├── Panel/                                  adjuntos y notas de tareas del panel: <AAAA-MM-DD> <tarea>/
└── _backups/
    └── redis/                              rdb diarios del Redis de la fábrica (últimas 14)
```

Fuera de `Nebulabs/` queda lo **personal** (Audi, Bautizo Noa, BUDAPEST, COUSAS NESTOR,
Fotos SD Araño, CV, DNI, Excel viejos…) y lo que Néstor tiene pendiente de decidir
(Discos navidad, fotos-ciclo, Canciones_con_mi_voz, Google AI Studio).

> **Nota TIKTOK_EDITOR / TIKTOK_SHOP:** no se han renombrado a propósito. La cuenta de servicio
> (`drive_sharing.py`) y nebulabs-media buscan `TIKTOK_EDITOR` por NOMBRE (`DRIVE_EDITOR_ROOT_NAME`);
> renombrarla exige cambiar esa variable y probar con un cliente. Pendiente de decidir con Néstor.

## Reglas para agentes

1. **Nada suelto en la raíz del Drive.** Todo lo de un proyecto va bajo `Nebulabs/<proyecto>/`.
2. **Pregunta antes de meter algo en `Nebulabs/TikTok/`**: está compartida (ver arriba).
   Datos internos (backups, chats, claves, consultas personales) nunca ahí.
3. **No escribas rutas a mano en el código ni en Redis.** En la Factory:
   `from src.rutas_drive import AI_PRO_REL, PROYECTO_REL, ruta` (vienen de
   `AI_PRO_DRIVE_DIR` / `NEBULABS_DRIVE_DIR`). Redis guarda `drive:<ruta relativa>`: lo
   hacen solas las bases Redis (`relativizar`/`absolutizar`).
4. **Notas y adjuntos de una tarea del panel:** `Nebulabs/Panel/<AAAA-MM-DD> <título>/`
   (el panel lo hace solo al adjuntar).
5. **Relevos y .md de trabajo** viven en el VPS (`~/relevos`, `docs/`), no en el Drive.
6. **Lo temporal** (renders, fotogramas, pruebas) va al disco ampliado del VPS
   (`/mnt/HC_Volume_106974679/agentes/trabajo/<tema>/`), no al Drive.

## Rutas viejas → nuevas

| Antes | Ahora |
|---|---|
| `NEBULABS_AUTOMATED_TIKTOK/` | `Nebulabs/TikTok/` |
| `NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/` | `Nebulabs/TikTok/TikTok Shop/` |
| `…/TIKTOK_SHOP_AI_PRO/FRUTINOVELAS/` | `Nebulabs/TikTok/Creator Reward/FrutiNovelas/` |
| `TIKTOK_SHOP_AI_PRO/` (la de la raíz) | `Nebulabs/TikTok/TikTok Shop/_raiz_antigua/` |
| `NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/` | `Nebulabs/TikTok/Creator Reward/` |
| `NEBULABS_AUTOMATED_TIKTOK/{BACKUPS_*,PAQUETE_*}` | `Nebulabs/TikTok/TikTok Shop/_curso/` |
| `MASTERPICKS_TIKTOK/` · `MASTERPICKS_COMPARATIVA/` | `Nebulabs/Master Picks/TikTok/` · `…/Comparativa/` |
| `MiPlayer_APK/` · `MoraTV/` · `_backups/mora-tv/` | `Nebulabs/Mora TV/APK/` · `…/Maquetas/` · `…/copias/` |
| `fit9ness-whoop/` · `Health_Motion/` | `Nebulabs/Fit9ness/whoop/` · `…/Health Motion/` |
| `_consultas/` | `Nebulabs/Asistentes/` |
| `CLAUDE_CHATS_BACKUP/` | `Nebulabs/Agentes/backups_chats/` |
| `_backups/redis/` | `Nebulabs/_backups/redis/` |
| `Panel/Capturas/` | `Nebulabs/Panel/` |

## Estado (5/11/2026, madrugada)

Hecho y comprobado (todo movido dentro del Drive, server-side):
- Raíz → `Nebulabs/TikTok` (mismo ID; permisos de bugalleitor, `Nebulabs` y `nebulabs-editor`
  intactos) y Programa 4 → `TikTok Shop`. Redis migrado a `drive:` (6.594 de 6.696 rutas existen;
  las 102 restantes ya faltaban antes: carpetas del Programa 2 y fotos de productos movidos).
  Mis tandas › Fotos ve lo mismo que antes: ness 143 carruseles / 462 fotos, nestor2 1 / 3.
- `TIKTOK_CR` → `Creator Reward`, FRUTINOVELAS → `Creator Reward/FrutiNovelas`, material del
  curso → `TikTok Shop/_curso`, la AI Pro suelta → `TikTok Shop/_raiz_antigua`.
- Master Picks, Mora TV, Fit9ness, Asistentes, backups de chats y de Redis → `Nebulabs/…`.
  Lo que tenía enlaces compartidos (APK de Mora, `_consultas` de Ana) se MOVIÓ (conserva IDs);
  el resto se copió, se comprobó con `rclone check` y el original fue a la papelera del Drive.
- Panel (vps-webs): `CARPETA_DEF = "Nebulabs/Panel"`.

Copias de seguridad de esta migración (vps-trabajo):
`/mnt/HC_Volume_106974679/agentes/trabajo/drive-nebulabs/backups/` — dumps de Redis antes de
cada paso y `rutas-originales-*.json` para `python3 scripts/redis_rutas_relativas.py --restaurar`.

## Cómo mover algo más adelante

1. `rclone moveto "gdrive:VIEJO" "gdrive:NUEVO"` (server-side; conserva ID y compartidos).
2. Si el código lo usa: variable en `.env` del despliegue (`NEBULABS_DRIVE_DIR`, `AI_PRO_DRIVE_DIR`,
   `CR_DRIVE_DIR`, `CURSO_DRIVE_DIR`) o `DRIVE_ALIAS_JSON` para lo demás; recrear `api`.
3. `python3 scripts/redis_rutas_relativas.py` (simulación) y luego `--aplicar` con las mismas variables.
4. Actualizar este fichero.
