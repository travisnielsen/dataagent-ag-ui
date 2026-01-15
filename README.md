# Enterprise Data Agent

This is a sample application that demonstrates exploration of structured and unstructured data using and agentic retrieval and NL2SQL. It leverages [Microsoft Agent Framework](https://aka.ms/agent-framework) (MAF) as an agent orchestrator and [CopilotKit](https://www.copilotkit.ai/) for the core user experience. These two pieces work together using the MAF implementation of the AG-UI protocol in the [agent-framework-ag-ui](https://pypi.org/project/agent-framework-ag-ui/) package. The code used in this sample was originated from [this template](https://github.com/CopilotKit/with-microsoft-agent-framework-python) created by the CopilotKit team.

> [!IMPORTANT]
> There is a current limitation in `agent-framework-ag-ui` where thread IDs generated in CopilotKit are not passed to the server-side agent. This limitation is referenced in the following GitHub issues: [2517](https://github.com/microsoft/agent-framework/issues/2517), [2458](https://github.com/microsoft/agent-framework/issues/2458), and [2479](https://github.com/microsoft/agent-framework/issues/2479). As a result, this solution uses a customized version of Agent Framework based on updates from [PR 3136](https://github.com/microsoft/agent-framework/pull/3136) which helps to address scenarios where service-managed threads are needed. This sample also includes additional middleware customizations to address incompatibilities between AG-UI and the new responses API conversation flow.

## Prerequisites

- Azure OpenAI credentials (for the Microsoft Agent Framework agent)
- Python 3.12+
- uv
- Node.js 20+ 
- Any of the following package managers:
  - pnpm (recommended)
  - npm
  - yarn
  - bun

It is assumed you have administrative permissions to an Azure subscription as well as the ability to register applications in Entra ID.

## Getting Started

### Deploy Azure Infrastructure

Coming soon

### Install dependencies

Install dependencies using your preferred package manager:

   ```bash
   # Using pnpm (recommended)
   pnpm install

   # Using npm
   npm install

   # Using yarn
   yarn install

   # Using bun
   bun install
   ```

   > **Note:** This automatically sets up the Python environment as well. If you have manual issues, you can run: `npm run install:agent`

### Register an App ID in Entra ID

This repo supports user-level authentication to the agent API, which supports enterprise security as well as documenting user feedback. The application can be created using: [create-chat-app.ps1](scripts/create-chat-app.ps1). Be sure to sign-into your Entra ID tenant using `az login` first.

### Set environment variables

Using the output from the application enrollment script, set up your agent credentials. The backend automatically uses Azure when the Azure env vars below are present. Create an `.env` file inside the `agent` folder with one of the following configurations:
  
   ```env
   # Microsoft Foundry settings
   AZURE_OPENAI_ENDPOINT=https://[your-resource].services.ai.azure.com/
   AZURE_OPENAI_PROJECT_ENDPOINT=https://[your-resource].services.ai.azure.com/api/projects/[your-project]
   AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4o

   # Entra ID Authentication
   AZURE_AD_CLIENT_ID=[your-app-id]
   AZURE_AD_TENANT_ID=[your-tenant-id]
   ```

> [!IMPORTANT]
> The Entra ID section is optional. When the two environment variables are set, the API will require a valid token issued by the source tenant with the correct target scope. If you don't require user-level authorization to the API, you can delete this section.
 
Next, create a new `.env.local` file within the `frontend` directory and populate the values. You can use the [.env.example](frontend/.env.example) as a reference.

   ```env
   NEXT_PUBLIC_AZURE_AD_CLIENT_ID=your-client-id-here
   NEXT_PUBLIC_AZURE_AD_TENANT_ID=your-tenant-id-here
   ```

### Disabling Authentication (Development Only)

For local development or testing purposes, you can disable authentication entirely by setting the `AUTH_DISABLED` environment variable on both the API and frontend.

**API (.env file in the `api` folder):**
   ```env
   AUTH_DISABLED=true
   ```

**Frontend (.env.local file in the `frontend` folder):**
   ```env
   NEXT_PUBLIC_AUTH_DISABLED=true
   ```

> [!WARNING]
> Do NOT use `AUTH_DISABLED=true` in production environments. This setting allows anonymous access to the API without any authentication or authorization checks.

### Start the development server

The following commands can be used to start the enviroment locally:

   ```bash
   # Using pnpm
   pnpm dev

   # Using npm
   npm run dev

   # Using yarn
   yarn dev

   # Using bun
   bun run dev
   ```

   This will start both the UI and the Microsoft Agent Framework server concurrently.

## Available Scripts

The following scripts can also be run using your preferred package manager:

- `dev` – Starts both UI and agent servers in development mode
- `dev:debug` – Starts development servers with debug logging enabled
- `dev:ui` – Starts only the Next.js UI server
- `dev:agent` – Starts only the Microsoft Agent Framework server
- `build` – Builds the Next.js application for production
- `start` – Starts the production server
- `lint` – Runs ESLint for code linting
- `install:agent` – Installs Python dependencies for the agent

## AG-UI and CopilotKit Features

This application demonstrates several key features from the [AG-UI protocol](https://docs.ag-ui.com/) and [CopilotKit](https://docs.copilotkit.ai/):

| Feature | Used? | Details |
|---------|-------|---------|
| **Agentic Chat** | ✅ Yes | `useCopilotAction` with handlers like `reload_all_flights`, `fetch_flight_details` that the LLM calls to execute frontend logic |
| **Backend Tool Rendering** | ✅ Yes | `useRenderToolCall` renders progress UI in the chat for backend tools (`fetch_flights`, `analyze_flights`, `clear_filter`, etc.) |
| **Human in the Loop** | ⚠️ Partial | `HumanInTheLoopOrchestrator` is in the orchestrator chain but no tools currently require approval |
| **Agentic Generative UI** | ❌ No | No long-running background tasks with streaming UI updates |
| **Tool-based Generative UI** | ⚠️ Partial | `useCopilotAction` with `render` exists for `display_flights`, `display_flight_details`, `display_historical_data` but actions are disabled with minimal output |
| **Shared State** | ✅ Yes | `useCoAgent` syncs `LogisticsAgentState` (including `activeFilter`) bidirectionally between frontend and Python agent |
| **Predictive State Updates** | ✅ Yes | `PREDICT_STATE_CONFIG` maps tool outputs to state for immediate UI updates before tool completion |

### Feature Examples

#### Agentic Chat (Frontend Actions)

Frontend actions allow the LLM to invoke client-side handlers:

```tsx
useCopilotAction({
  name: "reload_all_flights",
  description: "Clear all filters and load ALL flights into dashboard.",
  parameters: [{ name: "count", type: "number", required: false }],
  handler: async ({ count }) => {
    const flights = await refetchFlights({ limit: count || 100 });
    setDisplayFlights(flights);
    return `Dashboard now shows ${flights.length} flights.`;
  },
});
```

#### Backend Tool Rendering

Render custom UI in the chat when backend tools execute:

```tsx
useRenderToolCall({
  name: "fetch_flights",
  render: ({ args, status }) => (
    <div className="flex items-center gap-2 text-sm">
      {status !== 'complete' ? (
        <span>🔄 Fetching flights...</span>
      ) : (
        <span>✅ Loaded flights</span>
      )}
    </div>
  ),
});
```

#### Shared State

Bidirectional state sync between React and the Python agent:

```tsx
const { state, setState } = useCoAgent<LogisticsAgentState>({
  name: "logistics_agent",
  initialState: initialLogisticsState,
});

// React to agent state changes
useEffect(() => {
  if (state.activeFilter) {
    refetchFlights(state.activeFilter);
  }
}, [state.activeFilter]);
```

#### Predictive State Updates

Map backend tool outputs to state for instant UI feedback:

```python
PREDICT_STATE_CONFIG = {
    "activeFilter": {
        "tool": "fetch_flights",
        "tool_argument": "activeFilter",
    },
}
```

#### Backend Tools

Python tools the LLM can invoke via the agent:

```python
@ai_function(
    name="fetch_flights",
    description="Load and filter flights in the dashboard.",
)
def fetch_flights(
    route_from: Annotated[str | None, Field(description="Origin airport code")] = None,
    route_to: Annotated[str | None, Field(description="Destination airport code")] = None,
) -> dict:
    return {"message": "Loading flights...", "activeFilter": {...}}
```
