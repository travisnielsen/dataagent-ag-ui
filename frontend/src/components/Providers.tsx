"use client";

import { MsalAuthProvider } from "@/components/MsalAuthProvider";

/**
 * Root providers for the application.
 * Note: CopilotKit is NOT included here - each page should wrap its content
 * with AuthenticatedCopilotKit to specify which agent to use.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MsalAuthProvider>
      {children}
    </MsalAuthProvider>
  );
}
