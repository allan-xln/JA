const serverApiUrl = (
  process.env.SERVER_API_URL ||
  process.env.ELETROFRIO_API_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    turbotrace: {
      contextDirectory: process.cwd(),
      logLevel: "error",
      memoryLimit: 512,
      processCwd: process.cwd(),
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${serverApiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
