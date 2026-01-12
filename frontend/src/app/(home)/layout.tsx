"use client";

import { AuthenticatedCopilotKit } from "@/components/AuthenticatedCopilotKit";

export default function HomeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthenticatedCopilotKit agentName="my_agent">
      {children}
    </AuthenticatedCopilotKit>
  );
}
