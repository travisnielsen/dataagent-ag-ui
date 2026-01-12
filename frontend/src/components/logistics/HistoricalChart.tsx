import { HistoricalPayload } from '@/lib/logistics-types';

interface HistoricalChartProps {
  data: HistoricalPayload[];
  title?: string;
  themeColor: string;
  selectedRoute?: string | null;
}

export function HistoricalChart({ data, title = "Payload History & Predictions", themeColor, selectedRoute }: HistoricalChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-white/10 backdrop-blur-md rounded-xl p-6 w-full">
        <h2 className="text-xl font-bold text-white mb-4">{title}</h2>
        <p className="text-gray-300 text-center py-8">
          No historical data available. Ask about payload history for a flight!
        </p>
      </div>
    );
  }

  // Find max values for scaling
  const maxPounds = Math.max(...data.map(d => d.pounds));
  const maxCubicFeet = Math.max(...data.map(d => d.cubicFeet));
  const maxValue = Math.max(maxPounds, maxCubicFeet);

  // Scale factor for bar heights (max height = 180px)
  const maxHeight = 180;
  const scale = (value: number) => (value / maxValue) * maxHeight;

  return (
    <div className="bg-white/10 backdrop-blur-md rounded-xl p-6 w-full">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h2 className="text-xl font-bold text-white">{title}</h2>
          <p className="text-sm text-gray-400 mt-1">
            {selectedRoute ? (
              <span>Route: <span className="text-cyan-300 font-medium">{selectedRoute}</span></span>
            ) : (
              <span>All Routes (Aggregate)</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: themeColor }} />
            <span className="text-gray-300">Pounds</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-cyan-400" />
            <span className="text-gray-300">Cubic Ft</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-white/30 border border-dashed border-white" />
            <span className="text-gray-300">Predicted</span>
          </div>
        </div>
      </div>

      {/* Chart Container */}
      <div className="relative">
        {/* Y-axis labels */}
        <div className="absolute left-0 top-0 bottom-8 w-12 flex flex-col justify-between text-xs text-gray-400">
          <span>{maxValue.toLocaleString()}</span>
          <span>{(maxValue * 0.75).toLocaleString()}</span>
          <span>{(maxValue * 0.5).toLocaleString()}</span>
          <span>{(maxValue * 0.25).toLocaleString()}</span>
          <span>0</span>
        </div>

        {/* Bars Container */}
        <div className="ml-14 overflow-x-auto">
          <div className="flex items-end gap-2 min-w-max" style={{ height: `${maxHeight + 40}px` }}>
            {data.map((point, index) => (
              <div key={index} className="flex flex-col items-center">
                {/* Bars group */}
                <div className="flex items-end gap-1 mb-2" style={{ height: `${maxHeight}px` }}>
                  {/* Pounds bar */}
                  <div 
                    className={`w-6 rounded-t transition-all duration-300 ${point.predicted ? 'border-2 border-dashed border-white/50' : ''}`}
                    style={{ 
                      height: `${scale(point.pounds)}px`,
                      backgroundColor: point.predicted ? `${themeColor}80` : themeColor,
                    }}
                    title={`${point.pounds.toLocaleString()} lbs`}
                  />
                  {/* Cubic Feet bar */}
                  <div 
                    className={`w-6 rounded-t transition-all duration-300 ${point.predicted ? 'border-2 border-dashed border-white/50' : ''}`}
                    style={{ 
                      height: `${scale(point.cubicFeet)}px`,
                      backgroundColor: point.predicted ? 'rgba(34, 211, 238, 0.5)' : '#22d3ee',
                    }}
                    title={`${point.cubicFeet.toLocaleString()} cu ft`}
                  />
                </div>
                {/* Date label */}
                <span className={`text-xs ${point.predicted ? 'text-cyan-300' : 'text-gray-400'} whitespace-nowrap h-5`}>
                  {point.predicted && <span className="mr-1">📊</span>}
                  {point.date}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Grid lines */}
        <div className="absolute left-14 right-0 top-0 bottom-8 pointer-events-none">
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => (
            <div 
              key={i}
              className="absolute w-full border-t border-white/10"
              style={{ bottom: `${ratio * maxHeight}px` }}
            />
          ))}
        </div>
      </div>

      {/* Summary Stats */}
      <div className="mt-6 pt-4 border-t border-white/20 grid grid-cols-4 gap-4 text-center">
        <div>
          <p className="text-lg font-bold text-white">
            {Math.round(data.filter(d => !d.predicted).reduce((a, b) => a + b.pounds, 0) / data.filter(d => !d.predicted).length).toLocaleString()}
          </p>
          <p className="text-xs text-gray-400">Avg Lbs (Historical)</p>
        </div>
        <div>
          <p className="text-lg font-bold text-white">
            {Math.round(data.filter(d => !d.predicted).reduce((a, b) => a + b.cubicFeet, 0) / data.filter(d => !d.predicted).length).toLocaleString()}
          </p>
          <p className="text-xs text-gray-400">Avg Cu Ft (Historical)</p>
        </div>
        <div>
          <p className="text-lg font-bold text-cyan-300">
            {data.filter(d => d.predicted).length}
          </p>
          <p className="text-xs text-gray-400">Predicted Days</p>
        </div>
        <div>
          <p className="text-lg font-bold text-cyan-300">
            {data.filter(d => d.predicted).length > 0 
              ? Math.round(data.filter(d => d.predicted).reduce((a, b) => a + b.pounds, 0) / data.filter(d => d.predicted).length).toLocaleString()
              : 'N/A'}
          </p>
          <p className="text-xs text-gray-400">Predicted Avg Lbs</p>
        </div>
      </div>
    </div>
  );
}
