"""Obtiene un REFRESH TOKEN de Drive para la cuenta dueña (nebulabsaimedia).

Se ejecuta UNA sola vez en tu PC. Autorizas a la app a acceder a tu Drive y
te imprime el refresh token, que pegas en el `.env` del box como
`DRIVE_OAUTH_REFRESH_TOKEN`. Con él, el box emite URLs de subida resumable a
"Mi unidad" (los archivos los posee tu cuenta, con cuota).

Requisitos:
  1. Un cliente OAuth tipo **Aplicación de escritorio** en el proyecto GCP
     `nebulabs-editor` (APIs y servicios → Credenciales → Crear → ID de cliente
     OAuth → Aplicación de escritorio). Copia su Client ID y Client Secret.
  2. La **Google Drive API** habilitada en ese proyecto.
  3. `pip install google-auth-oauthlib`

Uso:
    python scripts/get_drive_refresh_token.py \
        --client-id TU_CLIENT_ID --client-secret TU_CLIENT_SECRET

Se abrirá el navegador → inicia sesión con **nebulabsaimedia@gmail.com** →
acepta el permiso de Drive. El refresh token se imprime al final.
"""

from __future__ import annotations

import argparse
import sys

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> int:
    # Consola de Windows (cp1252) no encodea emojis → forzamos UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Falta dependencia. Instala:  pip install google-auth-oauthlib")
        return 1

    client_config = {
        "installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # access_type=offline + prompt=consent garantiza que devuelva refresh_token.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        print("\n[!] No se obtuvo refresh_token. Revoca el acceso en "
              "https://myaccount.google.com/permissions y reintenta.")
        return 1

    print("\n" + "=" * 60)
    print("REFRESH TOKEN (pegalo en el .env del box):")
    print("\nDRIVE_OAUTH_REFRESH_TOKEN=" + creds.refresh_token)
    print("=" * 60)
    print("\nTambién necesitas en el .env del box:")
    print(f"DRIVE_OAUTH_CLIENT_ID={args.client_id}")
    print(f"DRIVE_OAUTH_CLIENT_SECRET={args.client_secret}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
