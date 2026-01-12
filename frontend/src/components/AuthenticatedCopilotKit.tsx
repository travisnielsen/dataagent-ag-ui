"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { useAccessToken } from "@/lib/useAccessToken";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { loginRequest } from "@/lib/msalConfig";

interface AuthenticatedCopilotKitProps {
  children: React.ReactNode;
}

/**
 * CopilotKit wrapper for the logistics agent with Azure AD authentication.
 * This component must be rendered inside MsalProvider context.
 * Uses Next.js API route as a proxy to forward requests with auth headers.
 */
export function AuthenticatedCopilotKit({ children }: AuthenticatedCopilotKitProps) {
  const { accessToken, isLoading } = useAccessToken();
  const isAuthenticated = useIsAuthenticated();
  const { instance } = useMsal();

  // Force sign-in if not authenticated
  const handleSignIn = async () => {
    try {
      await instance.loginRedirect(loginRequest);
    } catch (e) {
      console.error("Login failed:", e);
    }
  };

  // Show sign-in prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-4">
        <span>Please sign in to use the logistics agent</span>
        <button
          onClick={handleSignIn}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
        >
          Sign In
        </button>
      </div>
    );
  }

  // Show loading state while acquiring token
  if (isLoading && !accessToken) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <span>Authenticating...</span>
      </div>
    );
  }

  // If authenticated but no token (error state), show retry option
  if (!accessToken) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-4">
        <span>Unable to acquire access token</span>
        <button
          onClick={handleSignIn}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
        >
          Sign In Again
        </button>
      </div>
    );
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
  };

  // Use Next.js API route as a proxy to the backend
  // The proxy forwards requests to /logistics on the backend
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="logistics_agent"
      headers={headers}
    >
      {children}
    </CopilotKit>
  );
}
