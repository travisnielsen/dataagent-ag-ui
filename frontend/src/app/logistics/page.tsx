"use client";

import React, { useState } from "react";
import { AuthButton } from "@/components/AuthButton";
import { LogisticsAgentState, Flight, DashboardFilter, initialLogisticsState } from "@/lib/logistics-types";
import { useCoAgent, useCopilotAction } from "@copilotkit/react-core";
import { CopilotKitCSSProperties, CopilotChat } from "@copilotkit/react-ui";
import { FlightListCard } from "@/components/logistics/FlightListCard";
import { FlightDetailCard } from "@/components/logistics/FlightDetailCard";
import { HistoricalChart } from "@/components/logistics/HistoricalChart";
export default function LogisticsPage() {
  const [themeColor, setThemeColor] = useState("#1e3a5f"); // Dark navy blue for logistics

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
        "--copilot-kit-background-color": "#121b2c",
        "--copilot-kit-secondary-color": "#1a2535",
        "--copilot-kit-response-button-background-color": "#1a2535",
        "--copilot-kit-response-button-color": "#d1d5db",
        "--copilot-kit-contrast-color": "#ffffff",
        "--copilot-kit-secondary-contrast-color": "#d1d5db",
        "--copilot-kit-muted-color": "#9ca3af",
      } as CopilotKitCSSProperties}
      className="h-screen flex flex-col bg-gray-900"
    >
      {/* Navigation Bar */}
      <nav className="h-16 px-6 flex items-center justify-between border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-6">
          <span className="text-xl font-bold text-white">🪁 CopilotKit</span>
          <a href="/" className="text-gray-300 hover:text-white transition-colors">Home</a>
          <a href="/logistics" className="text-white font-medium transition-colors">Logistics</a>
          <a href="#" className="text-gray-300 hover:text-white transition-colors">Docs</a>
          <a href="#" className="text-gray-300 hover:text-white transition-colors">About</a>
        </div>
        <div className="flex items-center">
          <AuthButton />
        </div>
      </nav>

      {/* Two-column layout: Dashboard (70%) + Chat (30%) - swapped from home page */}
      <div className="flex justify-center items-center px-12 py-6" style={{ height: 'calc(100vh - 4rem)' }}>
        <div className="w-full max-w-7xl h-full flex gap-6">
          {/* Dashboard panel - 70% */}
          <LogisticsDashboard themeColor={themeColor} />

          {/* Chat panel - 30% */}
          <div className="w-[30%] h-full border border-gray-700 rounded-xl shadow-lg overflow-hidden flex-shrink-0">
            <CopilotChat
              className="h-full"
              labels={{
                title: "Logistics Assistant",
                initial: "📦 Hi there! I can help you analyze flight shipment data, identify utilization risks, and optimize your logistics operations."
              }}
              suggestions={[
                {
                  title: "Over-utilized Flights",
                  message: "Show me top 10 over-utilized flights for the next sort time",
                },
                {
                  title: "Under-utilized Flights",
                  message: "Show me top 10 under-utilized flights for the next sort time",
                },
                {
                  title: "LAX to ORD Route",
                  message: "Show me information for the LAX to ORD route",
                },
                {
                  title: "Predicted Payload",
                  message: "Show me predicted payload for upcoming flights",
                },
                {
                  title: "Flight Details",
                  message: "Show me payload for flight #LAX-ORD-2847",
                },
                {
                  title: "Utilization Risks",
                  message: "Show me all utilization risk flights",
                },
                {
                  title: "Historical Data",
                  message: "Show me historical payload trends for the last 7 days",
                }
              ]}
            />
          </div>
        </div>
      </div>
    </main>
  );
}

function LogisticsDashboard({ themeColor }: { themeColor: string }) {
  // Local state for UI controls to avoid controlled/uncontrolled issues
  const [highlightRisks, setHighlightRisks] = useState(true);
  const [maxFlights, setMaxFlights] = useState(10);

  // 🪁 Shared State: https://docs.copilotkit.ai/microsoft-agent-framework/shared-state
  const { state, setState } = useCoAgent<LogisticsAgentState>({
    name: "logistics_agent",
    initialState: initialLogisticsState,
  });

  // Debug: Log state changes
  React.useEffect(() => {
    console.log('[LogisticsDashboard] State changed:', {
      flightsCount: state.flights?.length ?? 0,
      historicalCount: state.historicalData?.length ?? 0,
      selectedFlight: state.selectedFlight?.flightNumber ?? null,
      activeFilter: state.activeFilter,
    });
  }, [state]);

  // 🪁 Generative UI: Render flight list from agent tool calls
  useCopilotAction({
    name: "display_flights",
    description: "Display a list of flights in the dashboard.",
    available: "disabled",
    parameters: [
      { name: "flights", type: "object[]", required: true },
    ],
    render: ({ args }) => {
      return (
        <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg">
          ✅ Updated dashboard with {args.flights?.length || 0} flights
        </div>
      );
    },
  }, []);

  // 🪁 Generative UI: Render flight detail card
  useCopilotAction({
    name: "display_flight_details",
    description: "Display detailed information for a specific flight.",
    available: "disabled",
    parameters: [
      { name: "flight", type: "object", required: true },
    ],
    render: ({ args }) => {
      if (!args.flight) return null;
      const flight = args.flight as Flight;
      return (
        <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg">
          ✅ Showing details for flight {flight.flightNumber}
        </div>
      );
    },
  }, [themeColor]);

  // 🪁 Generative UI: Render historical chart
  useCopilotAction({
    name: "display_historical_data",
    description: "Display historical payload data as a chart.",
    available: "disabled",
    parameters: [
      { name: "historicalData", type: "object[]", required: true },
      { name: "title", type: "string", required: false },
    ],
    render: ({ args }) => {
      return (
        <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg">
          📊 Updated chart with {args.historicalData?.length || 0} data points
        </div>
      );
    },
  }, [themeColor]);

  // 🪁 Frontend Action: Filter dashboard by route and/or utilization type
  useCopilotAction({
    name: "filter_dashboard",
    description: "Filter the Flight Shipments table and Payload History chart by route and/or utilization type. IMPORTANT: This tool ONLY filters data that is ALREADY loaded in the dashboard. If there is no data loaded yet, you MUST first call a data retrieval tool (like get_utilization_risks, get_over_utilized_flights, get_predicted_payload, etc.) to load data, THEN call this tool to filter it. Use this when the user asks to see data for a specific route (e.g., 'LAX to ORD') or utilization status (over-utilized, under-utilized). To clear filters, call with no parameters.",
    parameters: [
      { 
        name: "route", 
        type: "string", 
        description: "The route to filter by, e.g., 'LAX → ORD', 'LAX-ORD', or 'LAX to ORD'. Use airport codes.",
        required: false 
      },
      { 
        name: "utilizationType", 
        type: "string", 
        description: "Filter by utilization: 'over' for over-utilized (>85%), 'under' for under-utilized (<50%), or 'all' to show all.",
        required: false 
      },
    ],
    handler({ route, utilizationType }) {
      console.log('[filter_dashboard] HANDLER CALLED with:', { route, utilizationType });
      
      // Normalize route format: "LAX-ORD" or "LAX to ORD" -> "LAX → ORD"
      let normalizedRoute = route;
      if (route) {
        normalizedRoute = route
          .toUpperCase()
          .replace(/\s*-\s*/g, ' → ')
          .replace(/\s+TO\s+/gi, ' → ')
          .trim();
      }
      
      const filter: DashboardFilter = {
        route: normalizedRoute || null,
        utilizationType: (utilizationType as 'all' | 'over' | 'under') || null,
      };
      
      // Check if filter is effectively empty
      const hasFilter = filter.route || (filter.utilizationType && filter.utilizationType !== 'all');
      
      console.log('[filter_dashboard] Setting state:', { filter, hasFilter, normalizedRoute });
      
      // Use functional update to avoid stale closure issues
      setState((prevState) => ({
        ...prevState,
        activeFilter: hasFilter ? filter : null,
        selectedRoute: normalizedRoute || null,
      }));
      
      const result = hasFilter 
        ? `Dashboard filtered: ${filter.route ? `route ${filter.route}` : ''}${filter.route && filter.utilizationType ? ', ' : ''}${filter.utilizationType && filter.utilizationType !== 'all' ? `${filter.utilizationType}-utilized flights` : ''}`
        : 'Dashboard filters cleared.';
      
      console.log('[filter_dashboard] Returning result:', result);
      return result;
    },
    render: ({ args, status }) => {
      if (status === 'executing') {
        return (
          <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg animate-pulse">
            🔍 Applying filters...
          </div>
        );
      }
      const hasFilter = args.route || (args.utilizationType && args.utilizationType !== 'all');
      return (
        <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg">
          {hasFilter ? (
            <>🔍 Filtered: {args.route && <span className="text-cyan-300">{args.route}</span>}
            {args.route && args.utilizationType && args.utilizationType !== 'all' && ' • '}
            {args.utilizationType && args.utilizationType !== 'all' && (
              <span className={args.utilizationType === 'over' ? 'text-orange-300' : 'text-blue-300'}>
                {args.utilizationType === 'over' ? 'Over-utilized' : 'Under-utilized'}
              </span>
            )}</>
          ) : (
            <>✓ Showing all flights</>
          )}
        </div>
      );
    },
  }, [state, setState]);

  // Handle flight selection from the list (bi-directional state update)
  const handleSelectFlight = (flight: Flight) => {
    const selectedRoute = `${flight.from} → ${flight.to}`;
    setState({
      ...state,
      selectedFlight: flight,
      selectedRoute: selectedRoute,
      viewMode: 'detail',
    });
  };

  // Handle closing the detail view
  const handleCloseDetail = () => {
    setState({
      ...state,
      selectedFlight: null,
      selectedRoute: null,
      viewMode: 'list',
    });
  };

  // Detect if all displayed flights share the same route
  const getInferredRoute = (): string | null => {
    if (!state.flights || state.flights.length === 0) return null;
    
    const firstRoute = `${state.flights[0].from} → ${state.flights[0].to}`;
    const allSameRoute = state.flights.every(f => `${f.from} → ${f.to}` === firstRoute);
    
    return allSameRoute ? firstRoute : null;
  };

  // Get filtered historical data based on selected route or inferred route from flights
  const getFilteredHistoricalData = () => {
    if (!state.historicalData || state.historicalData.length === 0) return [];
    
    // Use explicitly selected route, or infer from displayed flights
    const activeRoute = state.selectedRoute || getInferredRoute();
    
    if (activeRoute) {
      // Filter to show only data for the active route
      const routeData = state.historicalData.filter(d => d.route === activeRoute);
      if (routeData.length > 0) return routeData;
    }
    
    // Show aggregate data (entries without a route specified)
    return state.historicalData.filter(d => !d.route);
  };

  // Get the active route for chart sub-heading
  const getActiveRoute = (): string | null => {
    return state.selectedRoute || getInferredRoute();
  };

  // Get filtered flights based on activeFilter
  const getFilteredFlights = () => {
    console.log('[getFilteredFlights] Called with:', {
      flightsCount: state.flights?.length ?? 0,
      activeFilter: state.activeFilter,
    });
    
    if (!state.flights || state.flights.length === 0) {
      console.log('[getFilteredFlights] No flights to filter');
      return [];
    }
    
    let filtered = [...state.flights];
    const filter = state.activeFilter;
    
    if (filter) {
      // Filter by route
      if (filter.route) {
        console.log('[getFilteredFlights] Filtering by route:', filter.route);
        filtered = filtered.filter(f => {
          const flightRoute = `${f.from} → ${f.to}`;
          const matches = flightRoute === filter.route;
          console.log(`[getFilteredFlights]   ${flightRoute} === ${filter.route}? ${matches}`);
          return matches;
        });
      }
      
      // Filter by utilization type
      if (filter.utilizationType && filter.utilizationType !== 'all') {
        if (filter.utilizationType === 'over') {
          // Over-utilized: high or critical risk (>85%)
          filtered = filtered.filter(f => f.riskLevel === 'high' || f.riskLevel === 'critical');
        } else if (filter.utilizationType === 'under') {
          // Under-utilized: low risk (<50%)
          filtered = filtered.filter(f => f.riskLevel === 'low');
        }
      }
    }
    
    console.log('[getFilteredFlights] Returning:', filtered.length, 'flights');
    return filtered;
  };

  return (
    <div
      style={{ backgroundColor: `${themeColor}15` }}
      className="w-[70%] h-full rounded-xl shadow-lg overflow-auto p-6 transition-colors duration-300 border border-gray-700"
    >
      <div className="flex flex-col gap-6 h-full">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              ✈️ Shipping Logistics Dashboard
            </h1>
            <p className="text-gray-400 text-sm mt-1">
              Real-time flight payload monitoring and utilization analysis
            </p>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <span>Show</span>
              <select
                value={maxFlights}
                onChange={(e) => setMaxFlights(Number(e.target.value))}
                className="bg-gray-700 border border-gray-600 text-white text-sm rounded px-2 py-1 focus:ring-sky-500 focus:border-sky-500"
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={15}>15</option>
                <option value={20}>20</option>
              </select>
              <span>flights</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={highlightRisks}
                onChange={(e) => setHighlightRisks(e.target.checked)}
                className="rounded border-gray-600 bg-gray-700 text-sky-500 focus:ring-sky-500"
              />
              Highlight Risks
            </label>
          </div>
        </div>

        {/* Active Filter Indicator */}
        {state.activeFilter && (
          <div className="flex items-center gap-2 px-3 py-2 bg-cyan-900/30 border border-cyan-700/50 rounded-lg">
            <span className="text-cyan-300 text-sm">🔍 Active Filter:</span>
            {state.activeFilter.route && (
              <span className="px-2 py-0.5 bg-cyan-700/50 rounded text-white text-sm">
                {state.activeFilter.route}
              </span>
            )}
            {state.activeFilter.utilizationType && state.activeFilter.utilizationType !== 'all' && (
              <span className={`px-2 py-0.5 rounded text-white text-sm ${
                state.activeFilter.utilizationType === 'over' ? 'bg-orange-700/50' : 'bg-blue-700/50'
              }`}>
                {state.activeFilter.utilizationType === 'over' ? 'Over-utilized' : 'Under-utilized'}
              </span>
            )}
            <button
              onClick={() => setState({ 
                ...state, 
                activeFilter: null, 
                selectedRoute: null,
              })}
              className="ml-2 text-gray-400 hover:text-white text-sm"
            >
              ✕ Clear
            </button>
          </div>
        )}

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col gap-6 overflow-auto">
          {/* Flight List - Hidden when a flight is selected */}
          {!state.selectedFlight && (
            <FlightListCard
              flights={getFilteredFlights()}
              selectedFlightId={state.selectedFlight?.id}
              onSelectFlight={handleSelectFlight}
              highlightRisks={highlightRisks}
              themeColor={themeColor}
              pageSize={maxFlights}
            />
          )}

          {/* Selected Flight Detail */}
          {state.selectedFlight && (
            <FlightDetailCard
              flight={state.selectedFlight}
              themeColor={themeColor}
              onClose={handleCloseDetail}
            />
          )}

          {/* Historical Chart */}
          {state.historicalData && state.historicalData.length > 0 && (
            <HistoricalChart
              data={getFilteredHistoricalData()}
              themeColor={themeColor}
              selectedRoute={getActiveRoute()}
            />
          )}
        </div>

        {/* Empty state when no data */}
        {(!state.flights || state.flights.length === 0) && !state.selectedFlight && (!state.historicalData || state.historicalData.length === 0) && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-6xl mb-4">📦</div>
              <h2 className="text-xl font-semibold text-white mb-2">Ready to Analyze</h2>
              <p className="text-gray-400 max-w-md">
                Use the chat assistant to query flight data, view utilization risks, 
                and explore historical payload trends.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
