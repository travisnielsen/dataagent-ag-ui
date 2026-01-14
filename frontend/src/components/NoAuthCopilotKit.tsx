"use client";

import { CopilotKit } from "@copilotkit/react-core";

interface NoAuthCopilotKitProps {
  children: React.ReactNode;
}

/**
 * CopilotKit wrapper without authentication.
 * Use this when AUTH_DISABLED is set to bypass Azure AD authentication.
 * Uses Next.js API route as a proxy to forward requests to the backend.
 */
export function NoAuthCopilotKit({ children }: NoAuthCopilotKitProps) {
  // Use Next.js API route as a proxy to the backend
  // The proxy forwards requests to /logistics on the backend
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="logistics_agent"
    >
      {children}
    </CopilotKit>
  );
}
