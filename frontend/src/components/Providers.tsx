"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { MsalAuthProvider } from "@/components/MsalAuthProvider";
import { AuthenticatedCopilotKit } from "@/components/AuthenticatedCopilotKit";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MsalAuthProvider>
      <AuthenticatedCopilotKit>
        {children}
      </AuthenticatedCopilotKit>
    </MsalAuthProvider>
  );
}

