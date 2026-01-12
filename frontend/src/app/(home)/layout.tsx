"use client";

import { AuthenticatedCopilotKit } from "@/components/AuthenticatedCopilotKit";

export default function HomeLayout({
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
