"use client";

import { AuthenticatedCopilotKit } from "@/components/AuthenticatedCopilotKit";

export default function LogisticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthenticatedCopilotKit>
      {children}
    </AuthenticatedCopilotKit>
  );
}
