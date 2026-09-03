import type { NextConfig } from "next";

const developmentProxy = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8000/api/:path*',
      },
    ];
  },
};

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true
  },
  // Disable automatic trailing slash redirect for API routes
  trailingSlash: false,
  ...(process.env.NODE_ENV === 'development'
    ? developmentProxy
    : { output: 'export' as const }),
};

export default nextConfig;
