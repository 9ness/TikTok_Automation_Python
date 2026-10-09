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

const SECCIONES: { titulo: string; texto: string }[] = [
  {
    titulo: "Quiénes somos",
    texto:
      "Ama Shop, Viva Shop y Viva Salud son cuentas de contenido que publican vídeos de productos con enlaces de afiliado (Amazon, SHEIN). Esta herramienta solo publica el contenido de nuestras propias cuentas.",
  },
  {
    titulo: "Qué datos usamos",
    texto:
      "Solo los tokens de acceso que nos dan Pinterest, Instagram, Facebook y Threads para publicar en NUESTRAS cuentas, y las estadísticas de nuestras propias publicaciones (vistas, alcance, interacciones). No recogemos datos de otros usuarios ni de las personas que ven el contenido.",
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
    texto:
      "Si compras a través de un enlace, la tienda (Amazon, SHEIN) puede pagarnos una comisión sin coste extra para ti. Cada tienda aplica su propia política de privacidad y de cookies.",
  },
  {
    titulo: "Borrado y contacto",
    texto:
      "Para pedir el borrado de cualquier dato o hacer una consulta, escríbenos por mensaje directo a cualquiera de nuestras cuentas (@ama_shop_es, @vivashop_es).",
  },
];

const NOMBRES: Record<string, string> = {
  ama_shop: "Ama Shop",
  viva_shop: "Viva Shop",
  viva_salud: "Viva Salud",
};

export default function PrivacidadPage({ params }: { params: { cuenta: string } }) {
  const nombre = NOMBRES[params.cuenta] ?? params.cuenta;
  return (
    <main className="mx-auto max-w-2xl px-4 py-8 text-sm text-neutral-800 sm:py-12">
      <h1 className="mb-1 text-xl font-semibold sm:text-2xl">Política de privacidad · {nombre}</h1>
      <p className="mb-6 text-xs text-neutral-500">Última actualización: 9 de octubre de 2026</p>
      {SECCIONES.map((s) => (
        <section key={s.titulo} className="mb-5">
          <h2 className="mb-1 font-semibold">{s.titulo}</h2>
          <p className="break-words leading-relaxed">{s.texto}</p>
        </section>
      ))}
    </main>
  );
}
