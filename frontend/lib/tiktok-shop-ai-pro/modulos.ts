/** Los nichos del curso "TikTok Shop AI Pro", uno por módulo.
 *
 * Fuente única: de aquí salen TANTO los items de la sidebar COMO la portada y
 * el texto de cada página. Añadir un nicho nuevo = una entrada aquí + una
 * página de tres líneas que llame a `<NichoPendiente slug="..." />`.
 *
 * `drive` es la carpeta del Drive compartido del curso (Skool) donde está el
 * material de ese módulo — se apunta aquí para no tener que buscarla cada vez
 * que toque implementar el nicho.
 */

import {
  Crown,
  Film,
  Footprints,
  GalleryHorizontalEnd,
  Globe,
  Layers,
  Palette,
  Shirt,
  Target,
  type LucideIcon,
} from "lucide-react";

export type ModuloNicho = {
  /** Último segmento de la URL bajo /tiktok-shop-ai-pro/. */
  slug: string;
  /** Número de módulo en el curso — el operador los nombra así. */
  modulo: number;
  /** Etiqueta corta para la sidebar. */
  label: string;
  /** Título completo del módulo, tal cual aparece en Skool. */
  titulo: string;
  icon: LucideIcon;
  /** Carpeta del Drive compartido del curso, si la tiene. */
  drive?: string;
  /** De qué va el nicho, en una frase. */
  resumen: string;
  /** true cuando la herramienta ya existe (no muestra "pendiente"). */
  listo?: boolean;
};

export const MODULOS: ModuloNicho[] = [
  {
    slug: "nicho-pov-bof",
    modulo: 6,
    label: "Nicho POV BOF",
    titulo: "Creación de Nicho POV BOF",
    icon: Target,
    drive: "Nicho POV BOF",
    resumen:
      "Vídeos POV con el producto de protagonista: problema → solución en segundos.",
    listo: true,
  },
  {
    slug: "nicho-ropa",
    modulo: 7,
    label: "Nicho Ropa",
    titulo: "Creación de Nicho Ropa",
    icon: Shirt,
    drive: "Nicho Ropa Con Personas",
    resumen: "Estilo POV frente al espejo, grabándose con el móvil.",
    listo: true,
  },
  {
    slug: "nicho-ropa-sin-humanos",
    modulo: 8,
    label: "Nicho Ropa Sin Humanos",
    titulo: "Creación de Nicho Ropa Sin Humanos",
    icon: Layers,
    drive: "Nicho Ropa Sin Personas",
    resumen: "Ropa que vende sin mostrar caras: contenido limpio y de producto.",
    listo: true,
  },
  {
    slug: "nicho-general",
    modulo: 9,
    label: "Nicho General",
    titulo: "Creación de Nicho General",
    icon: Globe,
    drive: "Nicho General",
    resumen: "Nichos rentables en cualquier categoría, sin atarse a un vertical.",
  },
  {
    slug: "nicho-bof-cinematografico",
    modulo: 10,
    label: "Nicho Cinematográfico",
    titulo: "Creación de Nicho BOF Cinematográfico",
    icon: Film,
    drive: "Nicho Cinematografico",
    listo: true,
    resumen: "Convertir el producto en una historia visual con estética de cine.",
  },
  {
    slug: "nicho-gorras",
    modulo: 11,
    label: "Nicho Gorras",
    titulo: "Creación de Nicho de Gorras",
    icon: Crown,
    drive: "Nicho Gorras",
    listo: true,
    resumen: "Gorras: catálogo amplio, producción rápida y repetible.",
  },
  {
    slug: "nicho-zapatos",
    modulo: 12,
    label: "Nicho Zapatos",
    titulo: "Creación de Nicho Zapatos",
    icon: Footprints,
    drive: "Nicho Zapatos",
    resumen: "Calzado: demanda constante y contenido fácil de escalar.",
  },
  {
    slug: "creativos-profesionales",
    modulo: 13,
    label: "Creativos Pro",
    titulo: "Creación de Creativos Profesionales",
    icon: Palette,
    resumen: "Anuncios de alto CTR pensados para las reglas de TikTok Shop.",
      listo: true,
  },
  {
    slug: "carruseles",
    modulo: 14,
    label: "Carruseles",
    titulo: "Creación de Carruseles",
    icon: GalleryHorizontalEnd,
    drive: "Nicho Carruseles",
    resumen: "Carruseles que informan, enganchan y venden 24/7.",
  },
];

export function moduloPorSlug(slug: string): ModuloNicho | undefined {
  return MODULOS.find((m) => m.slug === slug);
}

/** Portada recortada del módulo (está en `frontend/public/`). */
export function portadaDe(slug: string): string {
  return `/tiktok-shop-ai-pro/modulos/${slug}.jpg`;
}
