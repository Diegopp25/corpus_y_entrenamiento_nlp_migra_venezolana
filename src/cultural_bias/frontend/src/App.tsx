import { useState } from 'react';
import { Navbar } from './components/Navbar';
import type { NavTab } from './components/Navbar';
import { SingleAnalyzer } from './components/SingleAnalyzer';
import { WebsiteScraper } from './components/WebsiteScraper';
import { CorpusDashboard } from './components/CorpusDashboard';
import { ModelEvaluation } from './components/ModelEvaluation';
import './App.css';

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('single');
  const [injectedText, setInjectedText] = useState<string | null>(null);

  const handleSendToAnalyzer = (text: string) => {
    setInjectedText(text);
    setActiveTab('single');
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#080a0f] text-slate-200 relative selection:bg-orange-500/30 selection:text-orange-200 overflow-x-hidden">
      {/* Subtle ambient lighting gradients in background */}
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[350px] bg-gradient-to-b from-orange-500/10 via-purple-500/5 to-transparent blur-3xl pointer-events-none -z-10" />

      {/* Centralized Hero Title and Segmented Navigation directly beneath */}
      <Navbar currentTab={activeTab} onSelectTab={setActiveTab} />

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 pb-16">
        {activeTab === 'single' && (
          <SingleAnalyzer
            key={injectedText || 'default'}
            initialText={injectedText || undefined}
          />
        )}

        {activeTab === 'scraper' && (
          <WebsiteScraper onSendToAnalyzer={handleSendToAnalyzer} />
        )}

        {activeTab === 'corpus' && <CorpusDashboard />}

        {activeTab === 'models' && <ModelEvaluation />}
      </main>

      {/* Minimalist Footer */}
      <footer className="border-t border-white/[0.06] py-6 px-4 text-center mt-auto">
        <div className="flex items-center justify-center gap-2 text-xs text-slate-500 flex-wrap">
          <span>Análisis computacional de sesgo cultural mediante modelos BETO de lenguaje</span>
          <span className="opacity-40">•</span>
          <span>Investigación en Medios Digitales de Colombia y México</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
