/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // standalone = bundle minimal con server.js + node_modules necesarios.
  // Permite imagen runtime ~100 MB en lugar de ~500 MB con npm install.
  output: "standalone",
  experimental: {
    typedRoutes: true,
  },
  async headers() {
    // Next marca las páginas prerenderizadas con `s-maxage=31536000`: UN AÑO.
    // El HTML es lo que apunta a los chunks de JS, así que un HTML viejo
    // carga código viejo — el operador veía la interfaz de hace dos
    // despliegues y creía que no se había subido.
    //
    // Los ficheros de `/_next/static` llevan hash en el nombre, así que esos
    // sí pueden cachearse para siempre; lo que no puede es el HTML.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Cache-Control", value: "no-cache, must-revalidate" },
        ],
      },
      {
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
