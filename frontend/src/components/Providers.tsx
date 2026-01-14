"use client";

import { MsalAuthProvider } from "@/components/MsalAuthProvider";

/**
 * Root providers for the application.
 * Note: CopilotKit is NOT included here - each page should wrap its content
 * with AuthenticatedCopilotKit (or NoAuthCopilotKit) to specify which agent to use.
 * 
 * When NEXT_PUBLIC_AUTH_DISABLED=true, MSAL provider is skipped.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  // Check if authentication is disabled via environment variable
  const isAuthDisabled = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

  // Skip MSAL provider when auth is disabled
  if (isAuthDisabled) {
    return <>{children}</>;
  }

  return (
    <MsalAuthProvider>
      {children}
    </MsalAuthProvider>
  );
}
