import React from 'react';

export interface RadarSeries {
  name: string;
  color: string;
  fillColor: string;
  values: number[]; // Array of values (0-100) corresponding to axes
}

interface RadarChartProps {
  axes: string[];
  series: RadarSeries[];
  size?: number;
}

export const RadarChart: React.FC<RadarChartProps> = ({ axes, series, size = 340 }) => {
  const center = size / 2;
  const radius = size * 0.38;
  const numAxes = axes.length;
  const angleStep = (Math.PI * 2) / numAxes;

  // Levels for background grid (25%, 50%, 75%, 100%)
  const levels = [0.25, 0.5, 0.75, 1.0];

  // Helper to compute (x, y) coordinates
  const getCoordinates = (valueNormalized: number, index: number) => {
    // Start at -90 degrees (top)
    const angle = -Math.PI / 2 + index * angleStep;
    const r = radius * valueNormalized;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle)
    };
  };

  return (
    <div className="mx-auto w-full max-w-[340px]">
      <svg className="h-auto w-full" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background Grid Polygons */}
        {levels.map((level, lIdx) => {
          const points = axes
            .map((_, i) => {
              const pt = getCoordinates(level, i);
              return `${pt.x},${pt.y}`;
            })
            .join(' ');

          return (
            <polygon
              key={lIdx}
              points={points}
              fill={lIdx === 1 ? 'rgba(139, 92, 246, 0.05)' : 'none'}
              stroke="#262c42"
              strokeWidth={lIdx === 1 ? 1.5 : 1}
              strokeDasharray={lIdx === 1 ? '3 3' : undefined}
            />
          );
        })}

        {/* 50% Threshold label */}
        <text
          x={center + 6}
          y={center - radius * 0.5 + 4}
          fill="#8b5cf6"
          fontSize="9"
          fontWeight="700"
        >
          50%
        </text>

        {/* Axis lines and text labels */}
        {axes.map((axisName, i) => {
          const outerPt = getCoordinates(1.0, i);
          const labelPt = getCoordinates(1.22, i);

          return (
            <g key={axisName}>
              <line
                x1={center}
                y1={center}
                x2={outerPt.x}
                y2={outerPt.y}
                stroke="#262c42"
                strokeWidth="1"
              />
              <text
                x={labelPt.x}
                y={labelPt.y}
                fill="#cbd5e1"
                fontSize="10"
                fontWeight="500"
                textAnchor="middle"
                dominantBaseline="central"
              >
                {axisName}
              </text>
            </g>
          );
        })}

        {/* Series Data Polygons */}
        {series.map((s) => {
          const points = s.values
            .map((val, i) => {
              const pt = getCoordinates(Math.max(0, Math.min(100, val)) / 100, i);
              return `${pt.x},${pt.y}`;
            })
            .join(' ');

          return (
            <g key={s.name}>
              <polygon
                points={points}
                fill={s.fillColor}
                stroke={s.color}
                strokeWidth="2.5"
                opacity="0.85"
              />
              {/* Dots at each point */}
              {s.values.map((val, i) => {
                const pt = getCoordinates(Math.max(0, Math.min(100, val)) / 100, i);
                return (
                  <circle
                    key={i}
                    cx={pt.x}
                    cy={pt.y}
                    r="3.5"
                    fill={s.color}
                    stroke="#0e1019"
                    strokeWidth="1.5"
                  />
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-2">
        {series.map((s) => (
          <div key={s.name} className="inline-flex items-center gap-2">
            <span className="size-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-slate-300">{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
