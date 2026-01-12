import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  serverExternalPackages: ["@copilotkit/runtime"],
};

export default nextConfig;
