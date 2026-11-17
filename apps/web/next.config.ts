import type { NextConfig } from "next";

// Previews normally come from this app's API content proxy (no presigned
// URLs). The only direct B2 URLs the browser can see are public object URLs
// (when B2_PUBLIC_URL_BASE is set on a public bucket), which use the
// <bucket>.s3.<region>.backblazeb2.com / s3.<region>.backblazeb2.com hosts.
const nextConfig: NextConfig = {
  transpilePackages: ["@qdrant-multitenant-rag-tiering/shared"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.backblazeb2.com",
      },
    ],
  },
};

export default nextConfig;
