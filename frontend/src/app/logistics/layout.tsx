"use client";

import { AuthenticatedCopilotKit } from "@/components/AuthenticatedCopilotKit";

export default function LogisticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthenticatedCopilotKit agentName="logistics_agent">
      {children}
    </AuthenticatedCopilotKit>
  );
}
