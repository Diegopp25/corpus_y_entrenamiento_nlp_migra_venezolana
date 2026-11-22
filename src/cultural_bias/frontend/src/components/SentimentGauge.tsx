import React from 'react';
import type { SentimentAnalysis } from '../types';

interface SentimentGaugeProps {
  sentiment: SentimentAnalysis;
}

export const SentimentGauge: React.FC<SentimentGaugeProps> = ({ sentiment }) => {
  const { prediction, scores, explanation } = sentiment;

  const getPredictionColorClass = () => {
    switch (prediction) {
      case 'Negativo':
        return 'text-red-400';
      case 'Positivo':
        return 'text-emerald-400';
      case 'Neutro':
      default:
        return 'text-slate-300';
    }
  };

  return (
    <div className="bg-[#10131d]/85 backdrop-blur-md border border-white/[0.08] rounded-2xl p-5 sm:p-6 shadow-xl shadow-black/40 transition-all hover:border-white/[0.14] flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="font-['Outfit'] text-[17px] font-semibold text-white tracking-tight">
            Sentimiento
          </h3>
          <span className="text-[11.5px] text-slate-400 bg-white/[0.05] border border-white/[0.08] px-2.5 py-1 rounded-md">
            Confianza: {Math.max(scores.negativo, scores.neutro, scores.positivo)}%
          </span>
        </div>

        <div className="mb-5">
          <span className="text-[15px] font-medium text-white">Predicción: </span>
          <span className={`text-[17px] font-bold ml-1.5 ${getPredictionColorClass()}`}>
            {prediction}
          </span>
        </div>

        <div className="flex flex-col gap-3.5">
          {/* Negativo */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-slate-200 font-medium">Negativo</span>
              <span className="font-semibold text-slate-100">{scores.negativo}%</span>
            </div>
            <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
              <div
                className="h-full bg-red-500 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${Math.min(100, scores.negativo)}%` }}
              />
            </div>
          </div>

          {/* Neutro */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-slate-200 font-medium">Neutro</span>
              <span className="font-semibold text-slate-100">{scores.neutro}%</span>
            </div>
            <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
              <div
                className="h-full bg-slate-500 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${Math.min(100, scores.neutro)}%` }}
              />
            </div>
          </div>

          {/* Positivo */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-slate-200 font-medium">Positivo</span>
              <span className="font-semibold text-slate-100">{scores.positivo}%</span>
            </div>
            <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${Math.min(100, scores.positivo)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {explanation && (
        <div className="mt-5 pt-3.5 border-t border-white/[0.07] text-xs text-slate-400 leading-relaxed">
          <p>{explanation}</p>
        </div>
      )}
    </div>
  );
};
