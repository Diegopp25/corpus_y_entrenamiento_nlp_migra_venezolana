import React from "react"
import { FileTextIcon, GlobeIcon, BarChart3Icon, CpuIcon } from "./Icons"

export type NavTab = "single" | "scraper" | "corpus" | "models"

interface HeroNavProps {
  currentTab: NavTab
  onSelectTab: (tab: NavTab) => void
}

export const Navbar: React.FC<HeroNavProps> = ({ currentTab, onSelectTab }) => {
  return (
    <header className="flex flex-col items-center justify-center text-center pt-12 sm:pt-14 pb-8 px-4 max-w-4xl mx-auto w-full">
      {/* Centralized Clean Title */}
      <div className="flex flex-col items-center gap-3 mb-7">
        <h1 className="font-['Outfit'] text-3xl sm:text-4xl md:text-[42px] font-extrabold tracking-tight leading-[1.15] text-balance bg-gradient-to-b from-white via-slate-100 to-slate-400 bg-clip-text text-transparent drop-shadow-sm">
          Detector de sesgo en la cobertura de la migración venezolana
        </h1>
      </div>

      {/* Segmented Controls / Navigation Options centered right below the title */}
      <nav
        className="inline-flex items-center gap-1.5 p-1.5 rounded-full bg-[#121622]/80 backdrop-blur-xl border border-white/[0.08] shadow-2xl shadow-black/50 overflow-x-auto"
        aria-label="Secciones del sistema"
      >
        <button
          type="button"
          className={`inline-flex items-center gap-2 px-4 sm:px-5 py-2 rounded-full text-xs sm:text-[13.5px] font-medium transition-all duration-200 whitespace-nowrap ${
            currentTab === "single"
              ? "bg-white text-slate-950 font-bold shadow-md shadow-white/20"
              : "text-slate-400 hover:text-white hover:bg-white/[0.06]"
          }`}
          onClick={() => onSelectTab("single")}
        >
          <FileTextIcon size={15} />
          <span>Analizador de Texto</span>
        </button>

        <button
          type="button"
          className={`inline-flex items-center gap-2 px-4 sm:px-5 py-2 rounded-full text-xs sm:text-[13.5px] font-medium transition-all duration-200 whitespace-nowrap ${
            currentTab === "scraper"
              ? "bg-white text-slate-950 font-bold shadow-md shadow-white/20"
              : "text-slate-400 hover:text-white hover:bg-white/[0.06]"
          }`}
          onClick={() => onSelectTab("scraper")}
        >
          <GlobeIcon size={15} />
          <span>Extractor por Sitio de Noticias</span>
        </button>

        <button
          type="button"
          className={`inline-flex items-center gap-2 px-4 sm:px-5 py-2 rounded-full text-xs sm:text-[13.5px] font-medium transition-all duration-200 whitespace-nowrap ${
            currentTab === "corpus"
              ? "bg-white text-slate-950 font-bold shadow-md shadow-white/20"
              : "text-slate-400 hover:text-white hover:bg-white/[0.06]"
          }`}
          onClick={() => onSelectTab("corpus")}
        >
          <BarChart3Icon size={15} />
          <span>Comparativa Colombia vs. México</span>
        </button>

        <button
          type="button"
          className={`inline-flex items-center gap-2 px-4 sm:px-5 py-2 rounded-full text-xs sm:text-[13.5px] font-medium transition-all duration-200 whitespace-nowrap ${
            currentTab === "models"
              ? "bg-white text-slate-950 font-bold shadow-md shadow-white/20"
              : "text-slate-400 hover:text-white hover:bg-white/[0.06]"
          }`}
          onClick={() => onSelectTab("models")}
        >
          <CpuIcon size={15} />
          <span>Evaluación del Modelo</span>
        </button>
      </nav>
    </header>
  )
}
