import React from 'react';
import type { FrameScore } from '../types';

interface FramesBarChartProps {
  frames: FrameScore[];
  threshold?: number;
}

export const FramesBarChart: React.FC<FramesBarChartProps> = ({ frames, threshold = 50.0 }) => {
  const activeCount = frames.filter((f) => f.score >= threshold).length;

  return (
    <div className="bg-[#10131d]/85 backdrop-blur-md border border-white/[0.08] rounded-2xl p-5 sm:p-6 shadow-xl shadow-black/40 transition-all hover:border-white/[0.14] flex flex-col justify-between">
      <div>
        <div className="mb-4">
          <h3 className="font-['Outfit'] text-[17px] font-semibold text-white tracking-tight">
            Encuadres detectados
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {activeCount} de {frames.length} encuadres superan el umbral de {threshold}%
          </p>
        </div>

        <div className="flex flex-col gap-3">
          {frames.map((frame) => {
            const isActive = frame.score >= threshold;

            return (
              <div key={frame.id} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-slate-200">{frame.label}</span>
                    {isActive && (
                      <span className="bg-purple-600/90 text-white text-[10px] font-bold tracking-wider px-2 py-0.5 rounded shadow-sm shadow-purple-500/30">
                        ACTIVO
                      </span>
                    )}
                  </div>
                  <span
                    className={`text-xs font-semibold ${
                      isActive ? 'text-purple-300 font-bold' : 'text-slate-400'
                    }`}
                  >
                    {frame.score}%
                  </span>
                </div>

                <div className="w-full h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      isActive
                        ? 'bg-purple-600 shadow-[0_0_10px_rgba(147,51,234,0.5)]'
                        : 'bg-slate-600'
                    }`}
                    style={{ width: `${Math.min(100, frame.score)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
