"use client";

import { ProverbsCard } from "@/components/proverbs";
import { WeatherCard } from "@/components/weather";
import { MoonCard } from "@/components/moon";
import { AuthButton } from "@/components/AuthButton";
import { AgentState } from "@/lib/types";
import { useCoAgent, useCopilotAction } from "@copilotkit/react-core";
import { CopilotKitCSSProperties, CopilotChat } from "@copilotkit/react-ui";
import { useState } from "react";
export default function CopilotKitPage() {
  const [themeColor, setThemeColor] = useState("#6366f1");

  // 🪁 Frontend Actions: https://docs.copilotkit.ai/microsoft-agent-framework/frontend-actions
  useCopilotAction({
    name: "setThemeColor",
    parameters: [{
      name: "themeColor",
      description: "The theme color to set. Make sure to pick nice colors.",
      required: true, 
    }],
    handler({ themeColor }) {
      setThemeColor(themeColor);
    },
  });

  return (
    <main 
      style={{
        "--copilot-kit-primary-color": themeColor,
        "--copilot-kit-background-color": "#1f2937",
        "--copilot-kit-secondary-color": "#374151",
        "--copilot-kit-response-button-background-color": "#374151",
        "--copilot-kit-response-button-color": "#f9fafb",
        "--copilot-kit-contrast-color": "#f9fafb",
        "--copilot-kit-secondary-contrast-color": "#d1d5db",
      } as CopilotKitCSSProperties}
      className="h-screen flex flex-col bg-gray-900"
    >
      {/* Navigation Bar */}
      <nav className="h-16 px-6 flex items-center justify-between border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-6">
          <span className="text-xl font-bold text-white">🪁 CopilotKit</span>
          <a href="/" className="text-white font-medium transition-colors">Home</a>
          <a href="/logistics" className="text-gray-300 hover:text-white transition-colors">Logistics</a>
          <a href="#" className="text-gray-300 hover:text-white transition-colors">Docs</a>
          <a href="#" className="text-gray-300 hover:text-white transition-colors">About</a>
        </div>
        <div className="flex items-center">
          <AuthButton />
        </div>
      </nav>

      {/* Two-column layout: Chat (30%) + Content (70%) */}
      {/* Height = 100vh - nav (64px) - padding (48px top + bottom) */}
      <div className="flex justify-center items-center px-12 py-6" style={{ height: 'calc(100vh - 4rem)' }}>
        <div className="w-full max-w-7xl h-full flex gap-6">
          {/* Chat panel - 30% */}
          <div className="w-[30%] h-full border border-gray-700 rounded-xl shadow-lg overflow-hidden flex-shrink-0">
            <CopilotChat
              id="home-chat"
              className="h-full"
              labels={{
                title: "Chat Assistant",
                initial: "👋 Hi, there! You're chatting with an agent."
              }}
              suggestions={[
              {
                title: "Generative UI",
                message: "Get the weather in San Francisco.",
              },
              {
                title: "Frontend Tools",
                message: "Set the theme to green.",
              },
              {
                title: "Human In the Loop",
                message: "Please go to the moon.",
              },
              {
                title: "Write Agent State",
                message: "Add a proverb about AI.",
              },
              {
                title: "Update Agent State",
                message: "Please remove 1 random proverb from the list if there are any.",
              },
              {
                title: "Read Agent State",
                message: "What are the proverbs?",
              }
            ]}
          />
        </div>

        {/* Proverbs content - 70% */}
        <YourMainContent themeColor={themeColor} />
        </div>
      </div>
    </main>
  );
}

function YourMainContent({ themeColor }: { themeColor: string }) {
  // 🪁 Shared State: https://docs.copilotkit.ai/microsoft-agent-framework/shared-state
  const { state, setState } = useCoAgent<AgentState>({
    name: "my_agent",
    initialState: {
      proverbs: [
        "CopilotKit may be new, but its the best thing since sliced bread.",
      ],
    },
  })

  //🪁 Generative UI: https://docs.copilotkit.ai/microsoft-agent-framework/generative-ui
  useCopilotAction({
    name: "get_weather",
    description: "Get the weather for a given location.",
    available: "disabled",
    parameters: [
      { name: "location", type: "string", required: true },
    ],
    render: ({ args }) => {
      return <WeatherCard location={args.location} themeColor={themeColor} />
    },
  }, [themeColor]);

  // 🪁 Human In the Loop: https://docs.copilotkit.ai/microsoft-agent-framework/human-in-the-loop
  useCopilotAction({
    name: "go_to_moon",
    description: "Go to the moon on request. This action requires human approval and will render the MoonCard UI for confirmation.",
    available: "disabled",
    renderAndWaitForResponse: ({ respond, status}) => {
      return <MoonCard themeColor={themeColor} status={status} respond={respond} />
    },
  }, [themeColor]);

  return (
    <div
      style={{ backgroundColor: themeColor }}
      className="w-[70%] h-full rounded-xl shadow-lg overflow-auto flex justify-center items-center transition-colors duration-300"
    >
      <ProverbsCard state={state} setState={setState} />
    </div>
  );
}
