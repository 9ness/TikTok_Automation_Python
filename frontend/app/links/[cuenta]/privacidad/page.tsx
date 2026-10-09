import type { Metadata } from "next";

/** Política de privacidad PÚBLICA de cada cuenta
 *  (`links.nebulabsmedia.com/links/ama_shop/privacidad`): la piden las apps de
 *  Pinterest y Meta del publicador multiplataforma. Va bajo `/links/` porque es
 *  lo único que Caddy sirve en ese host sin login (el atajo `/<cuenta>` solo
 *  acepta un nivel). */
export const metadata: Metadata = {
  title: "Política de privacidad",
  robots: { index: false, follow: false },
};

type Cuenta = { nombre: string; tienda: string; instagram?: string };

/** Cada cuenta habla solo de sí misma: la política de Ama Shop no nombra a
 *  las otras dos (la lee Pinterest para la app de ESA cuenta). */
const CUENTAS: Record<string, Cuenta> = {
  ama_shop: { nombre: "Ama Shop", tienda: "SHEIN", instagram: "@ama_shop_es" },
  viva_shop: { nombre: "Viva Shop", tienda: "Amazon", instagram: "@vivashop_es" },
  viva_salud: { nombre: "Viva Salud", tienda: "Amazon" },
};

function secciones(c: Cuenta): { titulo: string; texto: string }[] {
  return [
    {
      titulo: "Quiénes somos",
      texto: `${c.nombre} es una cuenta de contenido que publica vídeos de productos con enlaces de afiliado de ${c.tienda}. Esta herramienta solo publica el contenido de nuestra propia cuenta.`,
    },
    {
      titulo: "Qué datos usamos",
      texto:
        "Solo los tokens de acceso que nos dan las plataformas (Pinterest, Instagram, Facebook, Threads) para publicar en NUESTRA cuenta, y las estadísticas de nuestras propias publicaciones (vistas, alcance, interacciones). No recogemos datos de otros usuarios ni de las personas que ven el contenido.",
    },
    {
      titulo: "Para qué",
      texto:
        "Para programar y publicar nuestros vídeos y medir cómo funcionan. No vendemos ni cedemos ningún dato a terceros.",
    },
    {
      titulo: "Dónde se guardan",
      texto:
        "Los tokens se guardan en nuestro servidor privado, con acceso restringido, y solo los usa el publicador. Se pueden revocar en cualquier momento desde la configuración de cada plataforma.",
    },
    {
      titulo: "Enlaces de afiliado",
      texto: `Si compras a través de un enlace, ${c.tienda} puede pagarnos una comisión sin coste extra para ti. ${c.tienda} aplica su propia política de privacidad y de cookies.`,
    },
    {
      titulo: "Borrado y contacto",
      texto: `Para pedir el borrado de cualquier dato o hacer una consulta, escríbenos por mensaje directo${c.instagram ? ` a ${c.instagram} en Instagram` : " a nuestra cuenta"}.`,
    },
  ];
}

export default function PrivacidadPage({ params }: { params: { cuenta: string } }) {
  const c = CUENTAS[params.cuenta] ?? { nombre: params.cuenta, tienda: "la tienda" };
  return (
    <main className="mx-auto max-w-2xl px-4 py-8 text-sm text-neutral-800 sm:py-12">
      <h1 className="mb-1 text-xl font-semibold sm:text-2xl">Política de privacidad · {c.nombre}</h1>
      <p className="mb-6 text-xs text-neutral-500">Última actualización: 9 de octubre de 2026</p>
      {secciones(c).map((s) => (
        <section key={s.titulo} className="mb-5">
          <h2 className="mb-1 font-semibold">{s.titulo}</h2>
          <p className="break-words leading-relaxed">{s.texto}</p>
        </section>
      ))}
    </main>
  );
}
