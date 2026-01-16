"use client";

import React, { useState, useEffect, useRef } from "react";
import { AuthButton } from "@/components/AuthButton";
import { LogisticsAgentState, Flight, DashboardFilter, initialLogisticsState, DataSummary, RecommendationsResult, FeedbackPayload } from "@/lib/logistics-types";
import { useLogisticsData } from "@/lib/useLogisticsData";
import { useCoAgent, useCopilotAction, useCoAgentStateRender, useRenderToolCall, useCopilotChat } from "@copilotkit/react-core";
import { useAgent } from "@copilotkit/react-core/v2";
import { CopilotKitCSSProperties, CopilotChat } from "@copilotkit/react-ui";
import { TextMessage, MessageRole } from "@copilotkit/runtime-client-gql";
import { FlightListCard } from "@/components/logistics/FlightListCard";
import { FlightDetailCard } from "@/components/logistics/FlightDetailCard";
import { HistoricalChart } from "@/components/logistics/HistoricalChart";
import { RiskBadge } from "@/components/logistics/RiskBadge";
export default function LogisticsPage() {
  const [themeColor, setThemeColor] = useState("#1e3a5f"); // Dark navy blue for logistics

  // Fetch summary data at the page level for the dynamic greeting
  const { summary, isLoading: summaryLoading } = useLogisticsData(100);

  // Build dynamic initial greeting based on summary data
  const getInitialGreeting = () => {
    if (summaryLoading || !summary) {
      return "📦 Hi there! I can help you analyze flight shipment data, identify utilization risks, and optimize your logistics operations.";
    }
    
    const { riskBreakdown, totalFlights, averageUtilization } = summary;
    const atRisk = (riskBreakdown.high || 0) + (riskBreakdown.critical || 0);
    const underUtilized = riskBreakdown.low || 0;
    
    if (atRisk > 0) {
      return `📦 Welcome! I'm monitoring ${totalFlights} flights with **${atRisk} requiring attention** (${riskBreakdown.critical || 0} critical, ${riskBreakdown.high || 0} high risk). Average utilization is ${averageUtilization.toFixed(0)}%. How can I help?`;
    }
    
    return `📦 Welcome! I'm monitoring ${totalFlights} flights. Current utilization looks healthy at ${averageUtilization.toFixed(0)}% average. ${underUtilized > 0 ? `${underUtilized} flights are under-utilized.` : ''} How can I help?`;
  };

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

      {/* Two-column layout: Dashboard (70%) + Chat (30%) - responsive on smaller screens */}
      <div className="flex justify-center items-center px-4 md:px-12 py-4 md:py-6" style={{ height: 'calc(100vh - 4rem)' }}>
        <div className="w-full max-w-7xl h-full flex flex-col lg:flex-row gap-4 md:gap-6">
          {/* Dashboard panel - 70% on large screens, full width on smaller */}
          <LogisticsDashboard themeColor={themeColor} />

          {/* Chat panel - 30% on large screens, full width on smaller */}
          <div className="w-full lg:w-[30%] h-[40vh] lg:h-full border border-gray-700 rounded-xl shadow-lg overflow-hidden flex-shrink-0">
            <CopilotChat
              className="h-full"
              labels={{
                title: "Logistics Assistant",
                initial: getInitialGreeting()
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
  
  // 🚀 Agent running state - detect when LLM is processing for loading indicators
  const { agent } = useAgent({ agentId: "logistics_agent" });
  const isAgentRunning = agent?.isRunning ?? false;
  
  // Track when we're fetching data after activeFilter changes
  const [isFetchingData, setIsFetchingData] = useState(false);
  
  // Combined loading state: agent running OR fetching REST data
  const isUpdating = isAgentRunning || isFetchingData;
  
  // Default to 10 flights visible
  const getDefaultMaxFlights = () => {
    return 10;
  };
  
  const [maxFlights, setMaxFlights] = useState(getDefaultMaxFlights);

  // 🪁 REST Data Fetching: Load initial data from REST API
  const { 
    flights: initialFlights, 
    historicalData: initialHistorical, 
    summary,
    isLoading,
    error,
    totalFlights,
    refetchFlights,
    refetchHistorical,
  } = useLogisticsData(100);

  // Local display state - separate from CoAgent state to avoid sync issues
  const [displayFlights, setDisplayFlights] = useState<Flight[]>([]);
  const [displayHistorical, setDisplayHistorical] = useState<typeof initialHistorical>([]);
  const [displayFilter, setDisplayFilter] = useState<DashboardFilter | null>(null);
  const [selectedFlight, setSelectedFlight] = useState<Flight | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);

  // Sync initial data to display state
  useEffect(() => {
    if (initialFlights.length > 0 && displayFlights.length === 0) {
      console.log('[LogisticsDashboard] Setting initial display flights:', initialFlights.length);
      setDisplayFlights(initialFlights);
    }
  }, [initialFlights, displayFlights.length]);

  useEffect(() => {
    if (initialHistorical.length > 0 && displayHistorical.length === 0) {
      console.log('[LogisticsDashboard] Setting initial display historical:', initialHistorical.length);
      setDisplayHistorical(initialHistorical);
    }
  }, [initialHistorical, displayHistorical.length]);

  // 🪁 Shared State: https://docs.copilotkit.ai/microsoft-agent-framework/shared-state
  const { state, setState } = useCoAgent<LogisticsAgentState>({
    name: "logistics_agent",
    initialState: initialLogisticsState,
  });

  // 🚀 Render agent state progress in chat for better UX feedback
  useCoAgentStateRender<LogisticsAgentState>({
    name: "logistics_agent",
    render: ({ state: agentState }) => {
      // Show loading indicator when activeFilter is being set
      if (agentState?.activeFilter && isFetchingData) {
        const filter = agentState.activeFilter;
        const parts: string[] = [];
        if (filter.routeFrom) parts.push(filter.routeFrom);
        if (filter.routeTo) parts.push(`→ ${filter.routeTo}`);
        if (filter.utilizationType) parts.push(`(${filter.utilizationType})`);
        
        return (
          <div className="flex items-center gap-2 text-sm text-gray-400 py-1">
            <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            <span>Loading {parts.join(' ') || 'flights'}...</span>
          </div>
        );
      }
      return null;
    },
  });

  // Debug: Log state changes
  React.useEffect(() => {
    console.log('[LogisticsDashboard] Display state changed:', {
      flightsCount: displayFlights?.length ?? 0,
      historicalCount: displayHistorical?.length ?? 0,
      selectedFlight: selectedFlight?.flightNumber ?? null,
      displayFilter: displayFilter,
    });
  }, [displayFlights, displayHistorical, selectedFlight, displayFilter]);

  // 🪁 Render Backend Tool Calls: Show tool execution in chat
  // fetch_flights - filters and updates the dashboard
  useRenderToolCall({
    name: "fetch_flights",
    render: ({ args, status }) => {
      const filter = args as Record<string, unknown>;
      const parts: string[] = [];
      if (filter?.route_from) parts.push(filter.route_from as string);
      if (filter?.route_to) parts.push(`→ ${filter.route_to}`);
      if (filter?.utilization) parts.push(`(${filter.utilization})`);
      if (filter?.risk_level) parts.push(`[${filter.risk_level} risk]`);
      const filterDesc = parts.length > 0 ? parts.join(' ') : 'all flights';
      
      // Debug: Log render timing
      console.log('[useRenderToolCall fetch_flights]', { status, args: filter, filterDesc });
      
      return (
        <div className="flex items-center gap-2 text-sm p-2 my-1 rounded-lg bg-blue-500/10 border border-blue-500/20">
          {status !== 'complete' ? (
            <>
              <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              <span className="text-blue-300">Fetching {filterDesc}...</span>
            </>
          ) : (
            <>
              <span className="text-blue-400">🔍</span>
              <span className="text-blue-300">Loaded {filterDesc}</span>
            </>
          )}
        </div>
      );
    },
  });

  // analyze_flights - answers questions about displayed data
  useRenderToolCall({
    name: "analyze_flights",
    render: ({ args, status, result }) => {
      const params = args as Record<string, unknown>;
      const question = (params?.question as string) || 'flight data';
      
      return (
        <div className="flex items-start gap-2 text-sm p-2 my-1 rounded-lg bg-purple-500/10 border border-purple-500/20">
          {status !== 'complete' ? (
            <>
              <div className="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin mt-0.5" />
              <span className="text-purple-300">Analyzing: {question}...</span>
            </>
          ) : (
            <>
              <span className="text-purple-400">📊</span>
              <span className="text-purple-300">Analysis complete</span>
            </>
          )}
        </div>
      );
    },
  });

  // clear_filter - resets the dashboard filter
  useRenderToolCall({
    name: "clear_filter",
    render: ({ status }) => (
      <div className="flex items-center gap-2 text-sm p-2 my-1 rounded-lg bg-orange-500/10 border border-orange-500/20">
        {status !== 'complete' ? (
          <>
            <div className="w-4 h-4 border-2 border-orange-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-orange-300">Clearing filters...</span>
          </>
        ) : (
          <>
            <span className="text-orange-400">🔄</span>
            <span className="text-orange-300">Filters cleared</span>
          </>
        )}
      </div>
    ),
  });

  // get_historical_payload - fetches historical data
  useRenderToolCall({
    name: "get_historical_payload",
    render: ({ args, status }) => {
      const params = args as Record<string, unknown>;
      const route = params?.route as string;
      
      return (
        <div className="flex items-center gap-2 text-sm p-2 my-1 rounded-lg bg-green-500/10 border border-green-500/20">
          {status !== 'complete' ? (
            <>
              <div className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
              <span className="text-green-300">Loading historical data{route ? ` for ${route}` : ''}...</span>
            </>
          ) : (
            <>
              <span className="text-green-400">📈</span>
              <span className="text-green-300">Historical data loaded{route ? ` for ${route}` : ''}</span>
            </>
          )}
        </div>
      );
    },
  });

  // get_predicted_payload - fetches predictions
  useRenderToolCall({
    name: "get_predicted_payload",
    render: ({ args, status }) => {
      const params = args as Record<string, unknown>;
      const route = params?.route as string;
      
      return (
        <div className="flex items-center gap-2 text-sm p-2 my-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
          {status !== 'complete' ? (
            <>
              <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
              <span className="text-cyan-300">Generating predictions{route ? ` for ${route}` : ''}...</span>
            </>
          ) : (
            <>
              <span className="text-cyan-400">🔮</span>
              <span className="text-cyan-300">Predictions ready{route ? ` for ${route}` : ''}</span>
            </>
          )}
        </div>
      );
    },
  });

  // 🪁 Backend Tool Rendering: Risk Mitigation Recommendations with Feedback
  // This renders an interactive card when the agent calls show_risk_recommendations
  useRenderToolCall({
    name: "show_risk_recommendations",
    render: function RecommendationsCard({ args, status, result }) {
      // Local state for feedback - single vote for all recommendations
      const [vote, setVote] = useState<'up' | 'down' | null>(null);
      const [comment, setComment] = useState('');
      const [submitted, setSubmitted] = useState(false);
      const [submitting, setSubmitting] = useState(false);

      // Loading state
      if (status !== 'complete') {
        return (
          <div className="p-4 my-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
              <span className="text-amber-300">Generating recommendations...</span>
            </div>
          </div>
        );
      }

      // Handle error or no result
      if (!result) {
        return (
          <div className="p-4 my-2 rounded-xl bg-red-500/10 border border-red-500/20">
            <span className="text-red-300">Unable to generate recommendations</span>
          </div>
        );
      }

      const data = result as RecommendationsResult;

      // Handle error from backend
      if ('error' in data && data.error) {
        return (
          <div className="p-4 my-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <span className="text-amber-300">{String(data.error)}</span>
          </div>
        );
      }

      // No recommendations needed (optimal utilization)
      if (!data.recommendations || data.recommendations.length === 0) {
        return (
          <div className="p-4 my-2 rounded-xl bg-green-500/10 border border-green-500/20">
            <div className="flex items-center gap-2">
              <span className="text-xl">✅</span>
              <div>
                <p className="text-green-300 font-medium">{data.flightNumber} - Optimal</p>
                <p className="text-green-400/80 text-sm">{data.message || `Flight is at ${data.utilizationPercent?.toFixed(1)}% utilization. No action needed.`}</p>
              </div>
            </div>
          </div>
        );
      }

      const handleVote = (newVote: 'up' | 'down') => {
        // Toggle off if same vote, otherwise set new vote
        setVote(prev => prev === newVote ? null : newVote);
      };

      const handleSubmit = async () => {
        if (!vote && !comment.trim()) {
          return; // Nothing to submit
        }

        setSubmitting(true);
        
        const payload: FeedbackPayload = {
          flightId: data.flightId,
          flightNumber: data.flightNumber,
          votes: vote ? { overall: vote } : {},
          comment: comment.trim() || undefined,
          timestamp: new Date().toISOString(),
        };

        try {
          const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
          const response = await fetch(`${apiUrl}/logistics/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });

          if (response.ok) {
            setSubmitted(true);
          } else {
            console.error('Failed to submit feedback:', await response.text());
          }
        } catch (error) {
          console.error('Error submitting feedback:', error);
        } finally {
          setSubmitting(false);
        }
      };

      // Determine card color based on risk level
      const isHighRisk = data.riskLevel === 'high' || data.riskLevel === 'critical';
      const cardBg = isHighRisk ? 'bg-red-500/10' : 'bg-blue-500/10';
      const cardBorder = isHighRisk ? 'border-red-500/30' : 'border-blue-500/30';
      const titleIcon = isHighRisk ? '⚠️' : '💡';
      const titleText = isHighRisk ? 'Risk Mitigation Recommendations' : 'Optimization Suggestions';

      return (
        <div className={`p-4 my-2 rounded-xl ${cardBg} border ${cardBorder} space-y-3`}>
          {/* Header */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xl">{titleIcon}</span>
              <h4 className="font-semibold text-white">{titleText}</h4>
            </div>
            <div className="flex items-center gap-2 pl-7">
              <span className="text-sm text-gray-300">{data.flightNumber}</span>
              <span className="text-sm text-gray-400">({data.route})</span>
            </div>
          </div>

          {/* Recommendations list */}
          <div className="space-y-2">
            {data.recommendations.map((rec) => (
              <div 
                key={rec.id} 
                className="p-3 bg-white/5 rounded-lg"
              >
                <span className="text-gray-200 text-sm">{rec.text}</span>
              </div>
            ))}
          </div>

          {/* Feedback section */}
          {!submitted ? (
            <div className="space-y-3 pt-3 border-t border-white/10">
              {/* Single vote for all recommendations */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Were these recommendations helpful?</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleVote('up')}
                    disabled={submitted}
                    className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
                      vote === 'up' 
                        ? 'bg-green-500/30 text-green-300 border border-green-500/50' 
                        : 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-green-300 border border-white/10'
                    }`}
                  >
                    <span>👍</span>
                    <span className="text-sm">Yes</span>
                  </button>
                  <button
                    onClick={() => handleVote('down')}
                    disabled={submitted}
                    className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
                      vote === 'down' 
                        ? 'bg-red-500/30 text-red-300 border border-red-500/50' 
                        : 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-red-300 border border-white/10'
                    }`}
                  >
                    <span>👎</span>
                    <span className="text-sm">No</span>
                  </button>
                </div>
              </div>

              {/* Comment field */}
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Additional feedback or suggestions... (optional)"
                className="w-full p-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 text-sm resize-none focus:outline-none focus:border-white/30"
                rows={2}
              />

              {/* Submit button */}
              <div className="flex justify-end">
                <button
                  onClick={handleSubmit}
                  disabled={submitting || (!vote && !comment.trim())}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                    submitting || (!vote && !comment.trim())
                      ? 'bg-gray-600 text-gray-400 cursor-not-allowed'
                      : 'bg-blue-500 hover:bg-blue-600 text-white'
                  }`}
                >
                  {submitting ? 'Submitting...' : 'Submit Feedback'}
                </button>
              </div>
            </div>
          ) : (
            <div className="pt-3 border-t border-white/10">
              <div className="flex items-center gap-2 text-green-400">
                <span>✓</span>
                <span className="text-sm">Thank you for your feedback!</span>
              </div>
            </div>
          )}
        </div>
      );
    },
  });

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

  // 🔄 React to state.activeFilter changes from backend fetch_flights tool
  // When the agent sets activeFilter via SSE, we fetch data via REST
  const [lastActiveFilter, setLastActiveFilter] = useState<string | null>(null);
  // Use ref for lastResolvedFilter to avoid stale closure issues in async callbacks
  const lastResolvedFilterRef = useRef<DashboardFilter | null>(null);
  
  useEffect(() => {
    const currentFilterStr = JSON.stringify(state.activeFilter);
    
    // Skip if filter hasn't changed (prevents re-fetch on other state changes)
    if (currentFilterStr === lastActiveFilter) {
      return;
    }
    
    // Skip initial null/undefined state
    if (!state.activeFilter && !lastActiveFilter) {
      return;
    }
    
    // IMPORTANT: Skip if activeFilter becomes undefined/null after having a real filter
    // This prevents the "flash" when state resets between requests
    // Only process explicit filter updates (objects with actual values)
    if (!state.activeFilter && lastResolvedFilterRef.current) {
      console.log('[activeFilter effect] Ignoring reset to undefined (keeping previous filter)');
      return;
    }
    
    console.log('[activeFilter effect] Filter changed:', state.activeFilter);
    setLastActiveFilter(currentFilterStr);
    
    // 🚀 Set fetching state immediately for responsive UI
    setIsFetchingData(true);
    
    // Fetch flights based on new filter
    const fetchData = async () => {
      const rawFilter = state.activeFilter;
      const prevFilter = lastResolvedFilterRef.current;
      
      // Resolve __KEEP__ sentinel values by merging with previous filter
      // This enables context-aware filtering (reset=false preserves existing values)
      const resolveValue = <T,>(newVal: T | "__KEEP__" | null | undefined, prevVal: T | null | undefined): T | undefined => {
        if (newVal === "__KEEP__") return prevVal as T | undefined;
        if (newVal === null || newVal === undefined) return undefined;
        return newVal;
      };
      
      const filter: DashboardFilter = {
        routeFrom: resolveValue(rawFilter?.routeFrom, prevFilter?.routeFrom) || null,
        routeTo: resolveValue(rawFilter?.routeTo, prevFilter?.routeTo) || null,
        utilizationType: resolveValue(rawFilter?.utilizationType, prevFilter?.utilizationType) || null,
        riskLevel: resolveValue(rawFilter?.riskLevel, prevFilter?.riskLevel) || null,
        dateFrom: resolveValue(rawFilter?.dateFrom, prevFilter?.dateFrom) || null,
        dateTo: resolveValue(rawFilter?.dateTo, prevFilter?.dateTo) || null,
        limit: rawFilter?.limit || prevFilter?.limit || 20,
      };
      
      console.log('[activeFilter effect] Resolved filter:', filter, '(from raw:', rawFilter, ', prev:', prevFilter, ')');
      lastResolvedFilterRef.current = filter;  // Update ref immediately
      
      try {
        const flights = await refetchFlights({
          limit: filter?.limit || 20,
          routeFrom: filter?.routeFrom || undefined,
          routeTo: filter?.routeTo || undefined,
          utilization: filter?.utilizationType as 'over' | 'near_capacity' | 'optimal' | 'under' | undefined,
          riskLevel: filter?.riskLevel as 'critical' | 'high' | 'medium' | 'low' | undefined,
          dateFrom: filter?.dateFrom || undefined,
          dateTo: filter?.dateTo || undefined,
          sortBy: 'utilizationPercent',
          sortDesc: filter?.utilizationType === 'over' || filter?.utilizationType === 'near_capacity' || !filter?.utilizationType,
        });
        
        console.log('[activeFilter effect] Fetched', flights.length, 'flights');
        
        // SYNC RESOLVED FILTER BACK TO AGENT STATE
        // This ensures the backend tools see the correct filter on the next request
        setState(prev => ({
          ...prev,
          activeFilter: filter,
        }));
        
        // Update display state
        setDisplayFlights(flights);
        setDisplayFilter(filter);
        setSelectedFlight(null);
        
        // Build route string for historical data
        const routeStr = filter?.routeFrom && filter?.routeTo 
          ? `${filter.routeFrom} → ${filter.routeTo}`
          : undefined;
        setSelectedRoute(routeStr || null);
        
        // Refresh historical data
        const historical = await refetchHistorical(routeStr);
        setDisplayHistorical(historical);
        
      } catch (err) {
        console.error('[activeFilter effect] Error fetching flights:', err);
      } finally {
        // 🚀 Clear fetching state when done
        setIsFetchingData(false);
      }
    };
    
    fetchData();
  }, [state.activeFilter, lastActiveFilter, setState, refetchFlights, refetchHistorical, setDisplayFlights, setDisplayFilter, setDisplayHistorical, setSelectedRoute, setSelectedFlight]);

  // 🪁 Frontend Action: Reload all flights (clear filters and refresh from REST API)
  useCopilotAction({
    name: "reload_all_flights",
    description: "COMMAND: Clear all filters and load ALL flights into dashboard. Use for: 'show all', 'refresh', 'reset'.",
    parameters: [
      { 
        name: "count", 
        type: "number", 
        description: "Number of flights to load (default 100, max 100)",
        required: false 
      },
    ],
    handler: async ({ count }) => {
      const limit = Math.min(count || 100, 100);
      console.log('[reload_all_flights] Reloading', limit, 'flights via REST API');
      
      try {
        const flights = await refetchFlights({ 
          limit,
          sortBy: 'utilizationPercent',
          sortDesc: true 
        });
        
        // Also refresh historical data
        const historical = await refetchHistorical();
        
        console.log('[reload_all_flights] Got', flights.length, 'flights and', historical.length, 'historical entries');
        
        // Clear all filters and update display state
        setDisplayFlights(flights);
        setDisplayHistorical(historical);
        setDisplayFilter(null);
        setSelectedRoute(null);
        setSelectedFlight(null);
        
        const critical = flights.filter(f => f.riskLevel === 'critical').length;
        const high = flights.filter(f => f.riskLevel === 'high').length;
        const medium = flights.filter(f => f.riskLevel === 'medium').length;
        const low = flights.filter(f => f.riskLevel === 'low').length;
        
        // Calculate route breakdown
        const routeCounts: Record<string, number> = {};
        flights.forEach(f => {
          const route = `${f.from} → ${f.to}`;
          routeCounts[route] = (routeCounts[route] || 0) + 1;
        });
        const topRoutes = Object.entries(routeCounts)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([route, count]) => `${route}: ${count}`)
          .join(', ');
        
        return `Dashboard now shows ${flights.length} flights. Risk: ${critical} critical, ${high} high, ${medium} medium, ${low} low. Top routes: ${topRoutes}. You can answer questions about this data without reloading.`;
      } catch (err) {
        console.error('[reload_all_flights] Error:', err);
        return `Error reloading flights: ${err instanceof Error ? err.message : 'Unknown error'}`;
      }
    },
    render: ({ args, status }) => {
      if (status === 'executing') {
        return (
          <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg animate-pulse">
            🔄 Reloading all flights...
          </div>
        );
      }
      return (
        <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg">
          ✅ Loaded all flights
        </div>
      );
    },
  }, [refetchFlights, refetchHistorical, setDisplayFlights, setDisplayHistorical, setDisplayFilter, setSelectedRoute, setSelectedFlight]);

  // NOTE: fetch_utilization_flights removed - use fetch_flights with utilization parameter instead
  // NOTE: fetch_flights_by_route removed - use fetch_flights with routeFrom/routeTo instead

  // 🪁 Frontend Action: Fetch flight details via REST API
  useCopilotAction({
    name: "fetch_flight_details",
    description: "Fetch details for a specific flight by flight number (e.g., LAX-ORD-1001) from the REST API.",
    parameters: [
      { 
        name: "flightNumber", 
        type: "string", 
        description: "The flight number to look up (e.g., LAX-ORD-1001)",
        required: true 
      },
    ],
    handler: async ({ flightNumber }) => {
      console.log(`[fetch_flight_details] Fetching flight ${flightNumber} via REST API`);
      
      try {
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${API_BASE_URL}/logistics/data/flights/${encodeURIComponent(flightNumber)}`);
        
        if (!response.ok) {
          throw new Error(`Failed to fetch flight: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (!data.flight) {
          return `Flight ${flightNumber} not found.`;
        }
        
        const flight = data.flight as Flight;
        
        // Update local display state to show flight detail
        setSelectedFlight(flight);
        setSelectedRoute(`${flight.from} → ${flight.to}`);
        
        // 🔄 Sync selected flight to agent state so LLM knows which flight is being viewed
        setState(prev => ({
          ...prev,
          selectedFlight: flight,
        }));
        
        return `Showing details for flight ${flight.flightNumber}. Utilization: ${flight.utilizationPercent}% (${flight.riskLevel} risk).`;
      } catch (err) {
        console.error('[fetch_flight_details] Error:', err);
        return `Error fetching flight: ${err instanceof Error ? err.message : 'Unknown error'}`;
      }
    },
    render: ({ args, status }) => {
      if (status === 'executing') {
        return (
          <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg animate-pulse">
            🔍 Looking up flight {args.flightNumber}...
          </div>
        );
      }
      return (
        <div className="text-sm text-gray-300 p-2 bg-white/10 rounded-lg">
          ✅ Loaded flight details for {args.flightNumber}
        </div>
      );
    },
  }, [setSelectedFlight, setSelectedRoute, setState]);

  // Hook for programmatic chat messages
  const { appendMessage } = useCopilotChat();

  // Handle flight selection from the list
  const handleSelectFlight = async (flight: Flight) => {
    setSelectedFlight(flight);
    setSelectedRoute(`${flight.from} → ${flight.to}`);
    
    // 🔄 Sync selected flight to agent state so LLM knows which flight is being viewed
    setState(prev => ({
      ...prev,
      selectedFlight: flight,
    }));

    // 🪁 Auto-trigger recommendations for flights that have them (high, critical, or low risk)
    const hasRecommendations = flight.riskLevel === 'high' || flight.riskLevel === 'critical' || flight.riskLevel === 'low';
    if (hasRecommendations) {
      // Small delay to ensure state is synced before sending message
      setTimeout(async () => {
        try {
          await appendMessage(
            new TextMessage({
              role: MessageRole.User,
              content: `Show recommendations for flight ${flight.flightNumber}`,
            })
          );
        } catch (err) {
          console.error('[handleSelectFlight] Error triggering recommendations:', err);
        }
      }, 100);
    }
  };

  // Handle closing the detail view
  const handleCloseDetail = () => {
    setSelectedFlight(null);
    setSelectedRoute(null);
    
    // 🔄 Clear selected flight in agent state
    setState(prev => ({
      ...prev,
      selectedFlight: null,
    }));
  };

  // Detect if all displayed flights share the same route
  const getInferredRoute = (): string | null => {
    if (!displayFlights || displayFlights.length === 0) return null;
    
    const firstRoute = `${displayFlights[0].from} → ${displayFlights[0].to}`;
    const allSameRoute = displayFlights.every(f => `${f.from} → ${f.to}` === firstRoute);
    
    return allSameRoute ? firstRoute : null;
  };

  // Get filtered historical data based on selected route or inferred route from flights
  const getFilteredHistoricalData = () => {
    if (!displayHistorical || displayHistorical.length === 0) return [];
    
    // Use explicitly selected route, or infer from displayed flights
    const activeRoute = selectedRoute || getInferredRoute();
    
    if (activeRoute) {
      // Filter to show only data for the active route
      const routeData = displayHistorical.filter(d => d.route === activeRoute);
      if (routeData.length > 0) return routeData;
    }
    
    // No route selected - aggregate data by date across all routes
    const aggregatedByDate = new Map<string, { date: string; pounds: number; cubicFeet: number; predicted: boolean }>();
    
    for (const entry of displayHistorical) {
      const existing = aggregatedByDate.get(entry.date);
      if (existing) {
        existing.pounds += entry.pounds;
        existing.cubicFeet += entry.cubicFeet;
        // Mark as predicted if any entry for that date is predicted
        if (entry.predicted) existing.predicted = true;
      } else {
        aggregatedByDate.set(entry.date, {
          date: entry.date,
          pounds: entry.pounds,
          cubicFeet: entry.cubicFeet,
          predicted: entry.predicted ?? false,
        });
      }
    }
    
    // Convert to array and sort by date
    return Array.from(aggregatedByDate.values()).sort((a, b) => a.date.localeCompare(b.date));
  };

  // Get the active route for chart sub-heading
  const getActiveRoute = (): string | null => {
    return selectedRoute || getInferredRoute();
  };

  // Get filtered flights based on displayFilter - memoized for proper React updates
  const filteredFlights = React.useMemo(() => {
    console.log('[filteredFlights] Computing with:', {
      flightsCount: displayFlights?.length ?? 0,
      displayFilter: displayFilter,
    });
    
    if (!displayFlights || displayFlights.length === 0) {
      console.log('[filteredFlights] No flights to filter');
      return [];
    }
    
    // Data is already filtered by the REST API, so just return displayFlights
    // The displayFilter is just for showing the UI state, not for re-filtering
    console.log('[filteredFlights] Returning:', displayFlights.length, 'flights');
    return displayFlights;
  }, [displayFlights, displayFilter]);

  return (
    <div
      style={{ backgroundColor: `${themeColor}15` }}
      className="w-full lg:w-[70%] min-h-[55vh] lg:h-full rounded-xl shadow-lg overflow-auto p-4 md:p-6 transition-colors duration-300 border border-gray-700"
    >
      <div className="flex flex-col gap-4 md:gap-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-0">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-white flex items-center gap-2">
              ✈️ Shipping Logistics Dashboard
            </h1>
            <p className="text-gray-400 text-xs md:text-sm mt-1">
              Real-time flight payload monitoring and utilization analysis
            </p>
          </div>
          <div className="flex items-center gap-3 md:gap-4 flex-wrap">
            <label className="flex items-center gap-2 text-xs md:text-sm text-gray-300">
              <span>Show</span>
              <select
                value={maxFlights}
                onChange={(e) => setMaxFlights(Number(e.target.value))}
                className="bg-gray-700 border border-gray-600 text-white text-xs md:text-sm rounded px-2 py-1 focus:ring-sky-500 focus:border-sky-500"
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={15}>15</option>
                <option value={20}>20</option>
              </select>
              <span>flights</span>
            </label>
            <label className="flex items-center gap-2 text-xs md:text-sm text-gray-300 cursor-pointer">
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
        {displayFilter && (
          <div className="flex items-center gap-2 px-3 py-2 bg-cyan-900/30 border border-cyan-700/50 rounded-lg flex-wrap">
            <span className="text-cyan-300 text-sm">🔍 Active Filter:</span>
            {displayFilter.routeFrom && (
              <span className="px-2 py-0.5 bg-cyan-700/50 rounded text-white text-sm">
                From: {displayFilter.routeFrom}
              </span>
            )}
            {displayFilter.routeTo && (
              <span className="px-2 py-0.5 bg-cyan-700/50 rounded text-white text-sm">
                To: {displayFilter.routeTo}
              </span>
            )}
            {displayFilter.utilizationType && displayFilter.utilizationType !== 'all' && (
              <span className={`px-2 py-0.5 rounded text-white text-sm ${
                {
                  over: 'bg-red-700/50',
                  near_capacity: 'bg-orange-700/50',
                  optimal: 'bg-green-700/50',
                  under: 'bg-blue-700/50'
                }[displayFilter.utilizationType] || 'bg-gray-700/50'
              }`}>
                {{
                  over: 'Over Capacity (>95%)',
                  near_capacity: 'Near Capacity (85-95%)',
                  optimal: 'Optimal (50-85%)',
                  under: 'Under-utilized (<50%)'
                }[displayFilter.utilizationType] || displayFilter.utilizationType}
              </span>
            )}
            {displayFilter.riskLevel && (
              <span className={`px-2 py-0.5 rounded text-white text-sm ${
                {
                  critical: 'bg-red-700/50',
                  high: 'bg-orange-700/50',
                  medium: 'bg-green-700/50',
                  low: 'bg-blue-700/50'
                }[displayFilter.riskLevel] || 'bg-gray-700/50'
              }`}>
                {displayFilter.riskLevel.charAt(0).toUpperCase() + displayFilter.riskLevel.slice(1)} Risk
              </span>
            )}
            {(displayFilter.dateFrom || displayFilter.dateTo) && (
              <span className="px-2 py-0.5 bg-purple-700/50 rounded text-white text-sm">
                {displayFilter.dateFrom === displayFilter.dateTo 
                  ? displayFilter.dateFrom 
                  : `${displayFilter.dateFrom || 'start'} – ${displayFilter.dateTo || 'end'}`}
              </span>
            )}
            {displayFilter.limit && (
              <span className="px-2 py-0.5 bg-gray-700/50 rounded text-gray-300 text-sm">
                Limit: {displayFilter.limit}
              </span>
            )}
            <button
              onClick={async () => {
                // Clear filters and reload all data
                setDisplayFilter(null);
                setSelectedRoute(null);
                
                // 🔄 IMPORTANT: Sync cleared filter to agent state so LLM knows filters are cleared
                // This ensures the agent's activeFilter matches the dashboard UI
                const clearedFilter = {
                  routeFrom: null,
                  routeTo: null,
                  utilizationType: null,
                  riskLevel: null,
                  dateFrom: null,
                  dateTo: null,
                  limit: 100,
                };
                setState(prev => ({
                  ...prev,
                  activeFilter: clearedFilter,
                }));
                lastResolvedFilterRef.current = clearedFilter;
                setLastActiveFilter(JSON.stringify(clearedFilter));
                
                try {
                  const flights = await refetchFlights({ limit: 100, sortBy: 'utilizationPercent', sortDesc: true });
                  const historical = await refetchHistorical();
                  setDisplayFlights(flights);
                  setDisplayHistorical(historical);
                } catch (err) {
                  console.error('Error clearing filters:', err);
                }
              }}
              className="ml-2 text-gray-400 hover:text-white text-sm"
            >
              ✕ Clear
            </button>
          </div>
        )}

        {/* Main Content Area - no internal scroll, dashboard scrolls instead */}
        <div className="flex-1 flex flex-col gap-6 min-h-0 relative">
          {/* 🚀 Loading overlay when agent is running or fetching data */}
          {/* Skip overlay when viewing flight details - recommendations load in chat instead */}
          {isUpdating && displayFlights.length > 0 && !selectedFlight && (
            <div className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-3 border-blue-400 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-gray-300">
                  {isAgentRunning ? 'Processing request...' : 'Loading flights...'}
                </span>
              </div>
            </div>
          )}
          
          {/* Flight List - Hidden when a flight is selected */}
          {!selectedFlight && (
            <FlightListCard
              key={`flights-${filteredFlights.length}-${filteredFlights[0]?.id ?? 'empty'}`}
              flights={filteredFlights}
              selectedFlightId={selectedFlight?.id}
              onSelectFlight={handleSelectFlight}
              highlightRisks={highlightRisks}
              themeColor={themeColor}
              pageSize={maxFlights}
              minItems={5}
            />
          )}

          {/* Selected Flight Detail */}
          {selectedFlight && (
            <FlightDetailCard
              flight={selectedFlight}
              themeColor={themeColor}
              onClose={handleCloseDetail}
            />
          )}

          {/* Historical Chart - Fixed minimum height */}
          {displayHistorical && displayHistorical.length > 0 && (
            <div className="min-h-[300px] h-[300px] flex flex-col">
              <HistoricalChart
                data={getFilteredHistoricalData()}
                themeColor={themeColor}
                selectedRoute={getActiveRoute()}
                fillHeight
              />
            </div>
          )}
        </div>

        {/* Empty state when no data */}
        {(!displayFlights || displayFlights.length === 0) && !selectedFlight && (!displayHistorical || displayHistorical.length === 0) && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              {isLoading ? (
                <>
                  <div className="text-6xl mb-4 animate-pulse">📦</div>
                  <h2 className="text-xl font-semibold text-white mb-2">Loading Data...</h2>
                  <p className="text-gray-400 max-w-md">
                    Fetching flight shipment data from the server.
                  </p>
                </>
              ) : error ? (
                <>
                  <div className="text-6xl mb-4">⚠️</div>
                  <h2 className="text-xl font-semibold text-red-400 mb-2">Error Loading Data</h2>
                  <p className="text-gray-400 max-w-md">
                    {error}
                  </p>
                  <p className="text-gray-500 text-sm mt-2">
                    Use the chat assistant to query data or try refreshing the page.
                  </p>
                </>
              ) : (
                <>
                  <div className="text-6xl mb-4">📦</div>
                  <h2 className="text-xl font-semibold text-white mb-2">Ready to Analyze</h2>
                  <p className="text-gray-400 max-w-md">
                    Use the chat assistant to query flight data, view utilization risks, 
                    and explore historical payload trends.
                  </p>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
