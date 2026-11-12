/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

// STATIC_EXPORT=1 builds plain files (frontend/out) that the API serves itself.
// This is how the desktop app is packaged: one process, one origin.
const nextConfig = process.env.STATIC_EXPORT
  ? { output: "export", images: { unoptimized: true } }
  : {
      // The browser only ever talks to this origin; API calls are proxied to the backend.
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
      },
    };

export default nextConfig;
