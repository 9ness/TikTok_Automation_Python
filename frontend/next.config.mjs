/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // standalone = bundle minimal con server.js + node_modules necesarios.
  // Permite imagen runtime ~100 MB en lugar de ~500 MB con npm install.
  output: "standalone",
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
