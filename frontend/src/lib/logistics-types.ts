// Logistics Agent State Types

export interface Flight {
  id: string;
  flightNumber: string;
  flightDate: string;
  from: string;
  to: string;
  currentCubicFeet: number;
  maxCubicFeet: number;
  currentPounds: number;
  maxPounds: number;
  utilizationPercent: number;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  sortTime: string;
}

export interface HistoricalPayload {
  date: string;
  cubicFeet: number;
  pounds: number;
  predicted?: boolean;
  route?: string; // e.g., "LAX → ORD"
}

export interface LogisticsAgentState {
  flights: Flight[];
  selectedFlight: Flight | null;
  historicalData: HistoricalPayload[];
  selectedRoute: string | null; // For filtering chart by route
  viewMode: 'list' | 'detail' | 'chart';
  highlightRisks: boolean;
  maxFlights: number;
}

// Demo date: January 11, 2026
// The mock data below uses this as the "current" date for demo consistency.
// The backend agent also uses this fixed date (see api/agents/logistics_agent.py DEMO_DATE).

// Initial mock flight data - multiple flights per route on different days
const initialFlights: Flight[] = [
  // LAX → ORD route (3 flights on different days)
  { id: 'flight-10001', flightNumber: 'LAX-ORD-3847', flightDate: '01/11/2026', from: 'LAX', to: 'ORD', currentPounds: 52000, maxPounds: 60000, currentCubicFeet: 4200, maxCubicFeet: 5000, utilizationPercent: 86.7, riskLevel: 'high', sortTime: '10:00' },
  { id: 'flight-10011', flightNumber: 'LAX-ORD-3921', flightDate: '01/12/2026', from: 'LAX', to: 'ORD', currentPounds: 48000, maxPounds: 60000, currentCubicFeet: 3900, maxCubicFeet: 5000, utilizationPercent: 80.0, riskLevel: 'high', sortTime: '10:00' },
  { id: 'flight-10012', flightNumber: 'LAX-ORD-4102', flightDate: '01/13/2026', from: 'LAX', to: 'ORD', currentPounds: 55000, maxPounds: 60000, currentCubicFeet: 4500, maxCubicFeet: 5000, utilizationPercent: 91.7, riskLevel: 'high', sortTime: '10:00' },
  
  // JFK → ATL route (3 flights on different days)
  { id: 'flight-10002', flightNumber: 'JFK-ATL-2156', flightDate: '01/11/2026', from: 'JFK', to: 'ATL', currentPounds: 38000, maxPounds: 55000, currentCubicFeet: 3100, maxCubicFeet: 4500, utilizationPercent: 69.1, riskLevel: 'medium', sortTime: '10:00' },
  { id: 'flight-10013', flightNumber: 'JFK-ATL-2287', flightDate: '01/12/2026', from: 'JFK', to: 'ATL', currentPounds: 42000, maxPounds: 55000, currentCubicFeet: 3400, maxCubicFeet: 4500, utilizationPercent: 76.4, riskLevel: 'medium', sortTime: '10:00' },
  { id: 'flight-10014', flightNumber: 'JFK-ATL-2398', flightDate: '01/13/2026', from: 'JFK', to: 'ATL', currentPounds: 35000, maxPounds: 55000, currentCubicFeet: 2800, maxCubicFeet: 4500, utilizationPercent: 63.6, riskLevel: 'medium', sortTime: '10:00' },
  
  // DFW → SFO route (2 flights)
  { id: 'flight-10003', flightNumber: 'DFW-SFO-4921', flightDate: '01/11/2026', from: 'DFW', to: 'SFO', currentPounds: 61000, maxPounds: 58000, currentCubicFeet: 4800, maxCubicFeet: 4600, utilizationPercent: 100, riskLevel: 'critical', sortTime: '10:00' },
  { id: 'flight-10015', flightNumber: 'DFW-SFO-5012', flightDate: '01/12/2026', from: 'DFW', to: 'SFO', currentPounds: 56000, maxPounds: 58000, currentCubicFeet: 4400, maxCubicFeet: 4600, utilizationPercent: 96.6, riskLevel: 'critical', sortTime: '10:00' },
  
  // SEA → MIA route (2 flights)
  { id: 'flight-10004', flightNumber: 'SEA-MIA-7834', flightDate: '01/11/2026', from: 'SEA', to: 'MIA', currentPounds: 22000, maxPounds: 65000, currentCubicFeet: 1800, maxCubicFeet: 5200, utilizationPercent: 33.8, riskLevel: 'low', sortTime: '10:00' },
  { id: 'flight-10016', flightNumber: 'SEA-MIA-7945', flightDate: '01/12/2026', from: 'SEA', to: 'MIA', currentPounds: 28000, maxPounds: 65000, currentCubicFeet: 2200, maxCubicFeet: 5200, utilizationPercent: 43.1, riskLevel: 'low', sortTime: '10:00' },
  
  // Other routes (single flights)
  { id: 'flight-10005', flightNumber: 'DEN-PHX-1293', flightDate: '01/11/2026', from: 'DEN', to: 'PHX', currentPounds: 45000, maxPounds: 52000, currentCubicFeet: 3600, maxCubicFeet: 4200, utilizationPercent: 86.5, riskLevel: 'high', sortTime: '10:00' },
  { id: 'flight-10006', flightNumber: 'ATL-LAX-5678', flightDate: '01/12/2026', from: 'ATL', to: 'LAX', currentPounds: 41000, maxPounds: 60000, currentCubicFeet: 3300, maxCubicFeet: 4800, utilizationPercent: 68.3, riskLevel: 'medium', sortTime: '14:00' },
  { id: 'flight-10007', flightNumber: 'ORD-JFK-9012', flightDate: '01/12/2026', from: 'ORD', to: 'JFK', currentPounds: 58000, maxPounds: 62000, currentCubicFeet: 4700, maxCubicFeet: 5000, utilizationPercent: 93.5, riskLevel: 'high', sortTime: '14:00' },
  { id: 'flight-10008', flightNumber: 'SFO-SEA-3456', flightDate: '01/12/2026', from: 'SFO', to: 'SEA', currentPounds: 18000, maxPounds: 48000, currentCubicFeet: 1500, maxCubicFeet: 3800, utilizationPercent: 37.5, riskLevel: 'low', sortTime: '14:00' },
  { id: 'flight-10009', flightNumber: 'MIA-DEN-7890', flightDate: '01/12/2026', from: 'MIA', to: 'DEN', currentPounds: 49000, maxPounds: 55000, currentCubicFeet: 4000, maxCubicFeet: 4400, utilizationPercent: 89.1, riskLevel: 'high', sortTime: '14:00' },
  { id: 'flight-10010', flightNumber: 'PHX-DFW-2345', flightDate: '01/13/2026', from: 'PHX', to: 'DFW', currentPounds: 35000, maxPounds: 50000, currentCubicFeet: 2800, maxCubicFeet: 4000, utilizationPercent: 70.0, riskLevel: 'medium', sortTime: '14:00' },
];

// Initial historical payload data by route (7 days history + 3 days predictions)
const initialHistoricalData: HistoricalPayload[] = [
  // Aggregate data (no route specified - shown when no flight selected)
  { date: '01/04', pounds: 420000, cubicFeet: 340000, predicted: false },
  { date: '01/05', pounds: 480000, cubicFeet: 390000, predicted: false },
  { date: '01/06', pounds: 450000, cubicFeet: 365000, predicted: false },
  { date: '01/07', pounds: 510000, cubicFeet: 410000, predicted: false },
  { date: '01/08', pounds: 470000, cubicFeet: 380000, predicted: false },
  { date: '01/09', pounds: 530000, cubicFeet: 430000, predicted: false },
  { date: '01/10', pounds: 490000, cubicFeet: 395000, predicted: false },
  { date: '01/12', pounds: 520000, cubicFeet: 420000, predicted: true },
  { date: '01/13', pounds: 540000, cubicFeet: 435000, predicted: true },
  { date: '01/14', pounds: 500000, cubicFeet: 405000, predicted: true },
  
  // LAX → ORD route historical data
  { date: '01/04', pounds: 48000, cubicFeet: 3800, predicted: false, route: 'LAX → ORD' },
  { date: '01/05', pounds: 52000, cubicFeet: 4100, predicted: false, route: 'LAX → ORD' },
  { date: '01/06', pounds: 49000, cubicFeet: 3900, predicted: false, route: 'LAX → ORD' },
  { date: '01/07', pounds: 55000, cubicFeet: 4400, predicted: false, route: 'LAX → ORD' },
  { date: '01/08', pounds: 51000, cubicFeet: 4050, predicted: false, route: 'LAX → ORD' },
  { date: '01/09', pounds: 54000, cubicFeet: 4300, predicted: false, route: 'LAX → ORD' },
  { date: '01/10', pounds: 50000, cubicFeet: 4000, predicted: false, route: 'LAX → ORD' },
  { date: '01/12', pounds: 53000, cubicFeet: 4250, predicted: true, route: 'LAX → ORD' },
  { date: '01/13', pounds: 56000, cubicFeet: 4500, predicted: true, route: 'LAX → ORD' },
  { date: '01/14', pounds: 52000, cubicFeet: 4150, predicted: true, route: 'LAX → ORD' },
  
  // JFK → ATL route historical data
  { date: '01/04', pounds: 35000, cubicFeet: 2800, predicted: false, route: 'JFK → ATL' },
  { date: '01/05', pounds: 39000, cubicFeet: 3100, predicted: false, route: 'JFK → ATL' },
  { date: '01/06', pounds: 37000, cubicFeet: 2950, predicted: false, route: 'JFK → ATL' },
  { date: '01/07', pounds: 41000, cubicFeet: 3300, predicted: false, route: 'JFK → ATL' },
  { date: '01/08', pounds: 38000, cubicFeet: 3050, predicted: false, route: 'JFK → ATL' },
  { date: '01/09', pounds: 40000, cubicFeet: 3200, predicted: false, route: 'JFK → ATL' },
  { date: '01/10', pounds: 36000, cubicFeet: 2900, predicted: false, route: 'JFK → ATL' },
  { date: '01/12', pounds: 42000, cubicFeet: 3350, predicted: true, route: 'JFK → ATL' },
  { date: '01/13', pounds: 44000, cubicFeet: 3500, predicted: true, route: 'JFK → ATL' },
  { date: '01/14', pounds: 40000, cubicFeet: 3200, predicted: true, route: 'JFK → ATL' },
  
  // DFW → SFO route historical data
  { date: '01/04', pounds: 55000, cubicFeet: 4300, predicted: false, route: 'DFW → SFO' },
  { date: '01/05', pounds: 58000, cubicFeet: 4550, predicted: false, route: 'DFW → SFO' },
  { date: '01/06', pounds: 57000, cubicFeet: 4450, predicted: false, route: 'DFW → SFO' },
  { date: '01/07', pounds: 60000, cubicFeet: 4700, predicted: false, route: 'DFW → SFO' },
  { date: '01/08', pounds: 59000, cubicFeet: 4600, predicted: false, route: 'DFW → SFO' },
  { date: '01/09', pounds: 62000, cubicFeet: 4850, predicted: false, route: 'DFW → SFO' },
  { date: '01/10', pounds: 58000, cubicFeet: 4550, predicted: false, route: 'DFW → SFO' },
  { date: '01/12', pounds: 61000, cubicFeet: 4750, predicted: true, route: 'DFW → SFO' },
  { date: '01/13', pounds: 63000, cubicFeet: 4900, predicted: true, route: 'DFW → SFO' },
  { date: '01/14', pounds: 59000, cubicFeet: 4600, predicted: true, route: 'DFW → SFO' },
  
  // SEA → MIA route historical data
  { date: '01/04', pounds: 20000, cubicFeet: 1600, predicted: false, route: 'SEA → MIA' },
  { date: '01/05', pounds: 24000, cubicFeet: 1900, predicted: false, route: 'SEA → MIA' },
  { date: '01/06', pounds: 22000, cubicFeet: 1750, predicted: false, route: 'SEA → MIA' },
  { date: '01/07', pounds: 26000, cubicFeet: 2100, predicted: false, route: 'SEA → MIA' },
  { date: '01/08', pounds: 23000, cubicFeet: 1850, predicted: false, route: 'SEA → MIA' },
  { date: '01/09', pounds: 25000, cubicFeet: 2000, predicted: false, route: 'SEA → MIA' },
  { date: '01/10', pounds: 21000, cubicFeet: 1700, predicted: false, route: 'SEA → MIA' },
  { date: '01/12', pounds: 27000, cubicFeet: 2150, predicted: true, route: 'SEA → MIA' },
  { date: '01/13', pounds: 29000, cubicFeet: 2300, predicted: true, route: 'SEA → MIA' },
  { date: '01/14', pounds: 25000, cubicFeet: 2000, predicted: true, route: 'SEA → MIA' },
];

export const initialLogisticsState: LogisticsAgentState = {
  flights: initialFlights,
  selectedFlight: null,
  historicalData: initialHistoricalData,
  selectedRoute: null,
  viewMode: 'list',
  highlightRisks: true,
  maxFlights: 10,
};

// Helper to get risk color based on level
export function getRiskColor(riskLevel: Flight['riskLevel']): string {
  switch (riskLevel) {
    case 'low':
      return '#3b82f6'; // blue - under-utilized
    case 'medium':
      return '#22c55e'; // green - optimal
    case 'high':
      return '#f97316'; // orange - approaching capacity
    case 'critical':
      return '#ef4444'; // red - over capacity
    default:
      return '#6b7280'; // gray
  }
}

// Helper to get risk label
export function getRiskLabel(riskLevel: Flight['riskLevel']): string {
  switch (riskLevel) {
    case 'low':
      return 'Under-utilized';
    case 'medium':
      return 'Optimal';
    case 'high':
      return 'Near Capacity';
    case 'critical':
      return 'Over Capacity';
    default:
      return 'Unknown';
  }
}
