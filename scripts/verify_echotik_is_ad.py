#!/usr/bin/env python
"""Verifica de una sentada si el Radar puede dejar de inferir GMV Max.

Contexto: hasta ahora `ads_signal` DEDUCÍA la inyección de ADS por proxy
(views altas + engagement bajo). EchoTik v3 expone `is_ad` (投流视频 =
"vídeo con inyección de tráfico pagado") en `echotik/video/list`, que es
el dato real. Y TikTok etiqueta AUTOMÁTICAMENTE los vídeos de afiliado de
un producto en campaña GMV Max **en la UE** → España incluida.

Este script contesta las 4 preguntas que deciden si pagamos el plan API:

  1. ¿Hay cuota? (el trial de 100 requests se agotó en junio 2026)
  2. ¿Funciona v3 para region=ES?          → la doc no lista regiones
  3. ¿`is_ad` viene POBLADO en España?     → LA pregunta que decide todo
  4. ¿`total_video_sale_cnt` sigue a 0?    → si sí, no hay ventas por vídeo

Uso (en el VPS, con el venv desplegado):

    ~/TikTok_Automation_Python/venv/bin/python scripts/verify_echotik_is_ad.py
    # opcional: pasar un product_id concreto ya conocido
    ... scripts/verify_echotik_is_ad.py 1729590000000000000

Coste: ~3-5 requests. NO imprime credenciales.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# El .env vive en el dir DESPLEGADO, no en el de trabajo.
for candidate in (
    os.path.expanduser("~/TikTok_Automation_Python/.env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
):
    if os.path.exists(candidate):
        load_dotenv(candidate)
        break

from src.tiktok_shop.api import echotik_cloud as ec  # noqa: E402

REGION = "ES"
OK, BAD, WARN = "✅", "❌", "⚠️"


def log(msg: str) -> None:
    print(f"    {msg}")


def main() -> int:
    if not ec.echotik_is_configured():
        print(f"{BAD} Sin ECHOTIK_API_USER / ECHOTIK_API_PASSWORD en el .env")
        return 2

    # ── 1. ¿Hay cuota? ───────────────────────────────────────────────
    print("\n═══ 1. ¿Queda cuota? ═══")
    product_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if not product_id:
        prods = ec.search_products("creatina", region=REGION, limit=10, log_callback=log)
        if ec.quota_exhausted():
            print(f"{BAD} SIN CUOTA — {ec.last_quota_error_msg()}")
            print("   → escribe a massif@echotik.live para ampliar el plan API.")
            return 1
        if not prods:
            print(f"{BAD} La búsqueda no devolvió productos (¿ES vacío?)")
            return 1
        print(f"{OK} Cuota OK — {len(prods)} productos ES")
        # Preferimos un producto con varios creadores: más vídeos que mirar.
        prods.sort(key=lambda p: int(p.get("total_video_cnt") or 0), reverse=True)
        product_id = str(prods[0].get("product_id") or "")
        print(f"    producto de prueba: {prods[0].get('product_name', '')[:60]!r}")
        print(f"    product_id={product_id} · vídeos={prods[0].get('total_video_cnt')}")
    else:
        print(f"{OK} Usando product_id pasado por argumento: {product_id}")

    if not product_id:
        print(f"{BAD} Sin product_id con el que probar")
        return 1

    # ── 2+3+4. La prueba clave: v3 + is_ad + ventas ──────────────────
    print("\n═══ 2-4. v3 `echotik/video/list` en ES: ¿is_ad? ¿ventas? ═══")
    vids = ec.get_product_ad_videos(product_id, region=REGION, limit=10, log_callback=log)

    if ec.quota_exhausted():
        print(f"{BAD} SIN CUOTA a mitad de prueba — {ec.last_quota_error_msg()}")
        return 1
    if not vids:
        print(f"{BAD} v3 `echotik/video/list` NO devolvió vídeos para region=ES.")
        print("   → o v3 no cubre ES, o el producto no tiene vídeos crawleados.")
        print("   → prueba otro product_id antes de descartar v3.")
        return 1

    print(f"{OK} v3 responde en ES — {len(vids)} vídeos\n")

    known = [v for v in vids if isinstance(v["ad_flag"], bool)]
    flagged = [v for v in known if v["ad_flag"]]
    with_sales = [v for v in vids if v["units_sold"] > 0]

    print("  ┌─ vídeo ────────────┬── views ──┬─ AD ─┬─ uds ─┐")
    for v in vids[:10]:
        ad = {True: " SÍ ", False: " no ", None: "  ? "}[v["ad_flag"]]
        print(f"  │ {v['video_id'][:18]:<18} │ {v['views']:>9,} │ {ad} │ {v['units_sold']:>5} │")
    print("  └────────────────────┴───────────┴──────┴───────┘\n")

    # ── VEREDICTO ────────────────────────────────────────────────────
    print("═══ VEREDICTO ═══")
    ok = True

    if not known:
        print(f"{BAD} `is_ad` NO viene poblado en ES → sigue sin haber etiqueta real.")
        print("   → el Radar tendría que seguir infiriendo por proxy. NO pagues por esto.")
        ok = False
    else:
        ratio = len(flagged) / len(known) * 100
        print(f"{OK} `is_ad` POBLADO: {len(known)}/{len(vids)} vídeos con etiqueta"
              f" · {len(flagged)} marcados AD ({ratio:.0f}%)")
        print("   → es la etiqueta lila de Kalodata, automatizable. Adelante.")

    if with_sales:
        print(f"{OK} `total_video_sale_cnt` poblado en {len(with_sales)}/{len(vids)} vídeos"
              " → ventas por vídeo disponibles (señal extra).")
    else:
        print(f"{WARN} `total_video_sale_cnt` = 0 en todos (como en el trial).")
        print("   → no bloquea: `is_ad` es la señal que importa.")

    # ── 5. Validación cruzada contra la etiqueta ORIGINAL de TikTok ──
    # `is_ad` lo calcula EchoTik y NO está documentado si lo lee de TikTok o
    # lo infiere. `realtime/video/detail` scrapea el vídeo en vivo y devuelve
    # los campos crudos del front-end → si coinciden, `is_ad` es de fiar.
    print("\n═══ 5. ¿El `is_ad` de EchoTik coincide con la etiqueta de TikTok? ═══")
    print("    (realtime/video/detail — 1 request por vídeo, muestreamos 3)")
    sample = [v for v in vids if isinstance(v["ad_flag"], bool)][:3] or vids[:3]
    agree = disagree = unknown = 0
    for v in sample:
        det = ec.get_video_ad_detail(v["video_id"], log_callback=log)
        if ec.quota_exhausted():
            print(f"{WARN} sin cuota a mitad del cruce — parcial")
            break
        if not det:
            unknown += 1
            print(f"    {v['video_id'][:18]}: realtime no devolvió detalle")
            continue
        real = det["any_commercial_label"]
        mine = v["ad_flag"]
        mark = OK if real == mine else BAD
        if mine is None:
            unknown += 1
            mark = WARN
        elif real == mine:
            agree += 1
        else:
            disagree += 1
        label = det["bc_label"] or "—"
        print(f"    {mark} {v['video_id'][:18]}: is_ad={mine} · TikTok: "
              f"is_ads={det['is_ads']} paid={det['is_paid_content']} "
              f"bct={det['branded_content_type']} etiqueta={label!r}")

    if agree and not disagree:
        print(f"{OK} `is_ad` COINCIDE con TikTok en {agree}/{agree} → señal de fiar.")
    elif disagree:
        print(f"{BAD} `is_ad` DISCREPA de TikTok en {disagree} de {agree + disagree}.")
        print("   → EchoTik estaría infiriendo. Usa realtime/video/detail como fuente.")
        ok = False
    else:
        print(f"{WARN} sin datos para cruzar ({unknown} desconocidos).")

    print("\n" + "═" * 60)
    print(f"{OK + ' ADELANTE — paga el plan API.' if ok else BAD + ' NO pagues todavía.'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
