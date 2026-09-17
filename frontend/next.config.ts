import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Output standalone untuk image Docker (frontend/Dockerfile multi-stage).
  // Tidak mengubah perilaku `npm run dev` / `next start` di host.
  output: "standalone",
};

export default nextConfig;
