"use client";

import { AuthenticatedCopilotKit } from "@/components/AuthenticatedCopilotKit";
import { NoAuthCopilotKit } from "@/components/NoAuthCopilotKit";

export default function LogisticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Check if authentication is disabled via environment variable
  const isAuthDisabled = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

  // Use NoAuthCopilotKit when authentication is disabled
  if (isAuthDisabled) {
    return (
      <NoAuthCopilotKit>
        {children}
      </NoAuthCopilotKit>
    );
  }

  return (
    <AuthenticatedCopilotKit>
      {children}
    </AuthenticatedCopilotKit>
  );
}
