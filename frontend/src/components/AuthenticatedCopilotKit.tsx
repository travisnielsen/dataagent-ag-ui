"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { useAccessToken } from "@/lib/useAccessToken";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { loginRequest } from "@/lib/msalConfig";
import { useEffect } from "react";

/**
 * CopilotKit wrapper that passes the access token to the runtime.
 * This component must be rendered inside MsalProvider context.
 */
export function AuthenticatedCopilotKit({ children }: { children: React.ReactNode }) {
  const { accessToken, isLoading, error } = useAccessToken();
  const isAuthenticated = useIsAuthenticated();
  const { instance } = useMsal();

  // If there's an auth error or no token when authenticated, prompt for login
  useEffect(() => {
    if (error) {
      console.error("Token acquisition error:", error);
    }
  }, [error]);

  // Force sign-in if not authenticated
  const handleSignIn = async () => {
    try {
      await instance.loginPopup(loginRequest);
    } catch (e) {
      console.error("Login failed:", e);
    }
  };

  // Show sign-in prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-4">
        <span>Please sign in to use the agent</span>
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

  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="my_agent"
      headers={headers}
    >
      {children}
    </CopilotKit>
  );
}
