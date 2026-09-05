# Nicho General — "UGC Desde 0"

Los prompts del formato que publicó el curso el 4 sep 2026 (Drive: `Nicho UGC
Desde 0`). Copiados de sus `.docx`, con marcadores para no tener cuatro copias
del mismo documento.

| Fichero | Qué es |
|---|---|
| `personaje.md` | Paso 0: recrear a la PERSONA desde una foto de Pinterest, de cuerpo entero sobre fondo blanco. Se hace una vez por personaje, no por producto |
| `guion_dolor.md` | Gancho **punto de dolor**: las tres escenas (imagen + vídeo Omni) |
| `guion_general.md` | Gancho **general**: el mismo documento salvo las escenas 1 y 2 |

Los marcadores los rellena `config.prompt_guion()`:

- `{{SEGUNDOS}}` · `{{TOTAL}}` · `{{CARACTERES}}` — 10 s en Omni (170 car) u
  8 s en GenAI Pro/Veo (136). **El guion de 8 s no es el de 10 recortado**: se
  escribe entero para caber, así que cada duración es otro vídeo.
- `{{EXTRAS}}` — lo que sabemos nosotros y el documento no: si el producto
  ofrece pago a plazos (su CTA lo nombra siempre, y aquí no hay arreglo
  posterior porque lo dice la persona del vídeo) y si quien habla es hombre o
  mujer, para que la identidad vocal no contradiga al personaje.
