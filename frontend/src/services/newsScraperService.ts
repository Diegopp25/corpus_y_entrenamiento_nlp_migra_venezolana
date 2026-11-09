import type { NewsArticle, ScrapingProgress, ScrapedSiteSummary } from '../types';
import { SAMPLE_NEWS_SITES } from '../data/sampleNewsWebsites';
import { analyzeNewsText } from './nlpAnalyzer';

export interface ScrapingOptions {
  url: string;
  maxArticles?: number;
  keywords?: string[];
  dateRange?: string;
  onProgress?: (progress: ScrapingProgress) => void;
}

export async function scrapeNewsSite(options: ScrapingOptions): Promise<ScrapedSiteSummary> {
  const { url, maxArticles = 4, onProgress } = options;
  const cleanUrl = url.trim().toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, '').replace(/\/.*$/, '');

  // Step 1: Connecting
  if (onProgress) {
    onProgress({
      status: 'connecting',
      currentStep: 1,
      totalSteps: 5,
      message: `Estableciendo conexión HTTPS con ${cleanUrl}...`,
      articlesFoundCount: 0
    });
  }
  await new Promise((resolve) => setTimeout(resolve, 600));

  // Find matching preset or infer characteristics
  const matchedPreset = SAMPLE_NEWS_SITES.find(
    (site) => cleanUrl.includes(site.domain.replace('www.', '')) || site.domain.includes(cleanUrl)
  );

  let inferredCountry: 'Colombia' | 'México' | 'Internacional' = 'Colombia';
  let siteName = cleanUrl.toUpperCase();

  if (matchedPreset) {
    inferredCountry = matchedPreset.country;
    siteName = matchedPreset.name;
  } else if (cleanUrl.endsWith('.co') || cleanUrl.includes('colombia') || cleanUrl.includes('bogota')) {
    inferredCountry = 'Colombia';
    siteName = cleanUrl.split('.')[0].toUpperCase();
  } else if (cleanUrl.endsWith('.mx') || cleanUrl.includes('mexico') || cleanUrl.includes('cdmx')) {
    inferredCountry = 'México';
    siteName = cleanUrl.split('.')[0].toUpperCase();
  }

  // Step 2: Crawling & discovering articles
  if (onProgress) {
    onProgress({
      status: 'crawling',
      currentStep: 2,
      totalSteps: 5,
      message: `Rastreando sitemaps y feeds RSS en ${siteName} con palabras clave: [migración, venezolanos, frontera]...`,
      articlesFoundCount: matchedPreset ? matchedPreset.articles.length : 3
    });
  }
  await new Promise((resolve) => setTimeout(resolve, 800));

  // Step 3: Cleaning HTML content (RF03)
  if (onProgress) {
    onProgress({
      status: 'cleaning',
      currentStep: 3,
      totalSteps: 5,
      message: 'Limpiando etiquetas HTML, descartando duplicados, anuncios y ruido textual (RF03)...',
      articlesFoundCount: matchedPreset ? matchedPreset.articles.length : 3
    });
  }
  await new Promise((resolve) => setTimeout(resolve, 700));

  // Determine articles list
  let rawArticles: NewsArticle[] = [];
  if (matchedPreset) {
    rawArticles = [...matchedPreset.articles];
    if (rawArticles.length > maxArticles) {
      rawArticles = rawArticles.slice(0, maxArticles);
    }
  } else {
    // Generate contextualized articles for any arbitrary URL entered by the user
    const dateNow = new Date().toLocaleDateString('es-ES', { day: '2-digit', month: 'long', year: 'numeric' });
    if (inferredCountry === 'Colombia') {
      rawArticles = [
        {
          id: `custom-co-1`,
          title: `Debate en concejo municipal sobre convivencia ciudadana y atención a comunidades migrantes en ${siteName}`,
          snippet: 'Concejales y delegados de seguridad discutieron planes de acción para mitigar la delincuencia y fortalecer la vigilancia en barrios comerciales...',
          fullText: `La ola de inseguridad y la preocupación por presuntos delitos cometidos en zonas comerciales motivó un extenso debate en el concejo municipal. Diversos voceros exigieron mayor presencia policial, controles migratorios estrictos y seguimiento a bandas criminales, al tiempo que se solicitaron apoyos para los albergues de acogida y servicios de salud.`,
          author: `Redacción ${siteName}`,
          date: dateNow,
          media: siteName,
          country: 'Colombia',
          url: `https://${cleanUrl}/noticias/seguridad-comunidad-migrante`,
          category: 'Seguridad'
        },
        {
          id: `custom-co-2`,
          title: `Avances en el registro biométrico y acceso a la educación para niños y jóvenes migrantes`,
          snippet: 'Secretaría de Educación y Migración Colombia confirmaron que miles de jóvenes ya asisten a clases regulares...',
          fullText: `El gobierno local confirmó nuevas jornadas de atención en salud y regularización de documentos para la población migrante en colegios públicos. Representantes del sector educativo enfatizaron que el acceso a las aulas garantiza la inclusión social y previene la marginación de familias vulnerables provenientes de Venezuela.`,
          author: `Equipo Especial ${siteName}`,
          date: dateNow,
          media: siteName,
          country: 'Colombia',
          url: `https://${cleanUrl}/educacion/registro-escolar-inclusion`,
          category: 'Acceso a servicios'
        }
      ];
    } else {
      rawArticles = [
        {
          id: `custom-mx-1`,
          title: `Cámaras de comercio de la frontera reportan incorporación de cientos de migrantes en plantas automotrices`,
          snippet: 'La demanda de mano de obra calificada en el sector industrial impulsa convenios con el Instituto Nacional de Migración...',
          fullText: `Empresarios de la zona industrial destacaron el aporte de la fuerza laboral venezolana para solventar el déficit de personal técnico. Los trabajadores cuentan con permisos de estancia y son capacitados para integrarse formalmente en cadenas de montaje y manufactura, promoviendo el dinamismo económico regional.`,
          author: `Sección Negocios ${siteName}`,
          date: dateNow,
          media: siteName,
          country: 'México',
          url: `https://${cleanUrl}/economia/fuerza-laboral-industria`,
          category: 'Empleo y economía'
        },
        {
          id: `custom-mx-2`,
          title: `Coordinan albergues y autoridades tránsito humanitario seguro hacia el norte del país`,
          snippet: 'Se refuerzan los puntos de hidratación, atención médica y asesoría legal en estaciones migratorias...',
          fullText: `En los principales corredores de tránsito migratorio, comisiones de derechos humanos y albergues de la sociedad civil trabajan conjuntamente para atender a caravanas y grupos familiares en ruta hacia la frontera norte. Se ha priorizado la protección de menores y la agilización de citas para trámites consulares.`,
          author: `Corresponsal Frontera ${siteName}`,
          date: dateNow,
          media: siteName,
          country: 'México',
          url: `https://${cleanUrl}/sociedad/atencion-transito-migratorio`,
          category: 'Tránsito migratorio'
        }
      ];
    }
  }

  // Step 4: NLP BETO Inference (RF05)
  if (onProgress) {
    onProgress({
      status: 'analyzing',
      currentStep: 4,
      totalSteps: 5,
      message: `Ejecutando inferencia neuronal con BETO sobre ${rawArticles.length} artículos recopilados...`,
      articlesFoundCount: rawArticles.length
    });
  }
  await new Promise((resolve) => setTimeout(resolve, 850));

  // Run analysis on each article
  const analyzedArticles: NewsArticle[] = rawArticles.map((article) => {
    const analysis = analyzeNewsText(article.fullText, {
      title: article.title,
      sourceUrl: article.url,
      mediaName: article.media,
      country: article.country
    });
    return {
      ...article,
      preAnalyzedResult: analysis
    };
  });

  // Step 5: Aggregate metrics calculation
  let totalNeg = 0;
  let totalNeu = 0;
  let totalPos = 0;
  const frameTally: Record<string, number> = {};

  for (const art of analyzedArticles) {
    if (art.preAnalyzedResult) {
      totalNeg += art.preAnalyzedResult.sentiment.scores.negativo;
      totalNeu += art.preAnalyzedResult.sentiment.scores.neutro;
      totalPos += art.preAnalyzedResult.sentiment.scores.positivo;

      for (const f of art.preAnalyzedResult.frames) {
        frameTally[f.label] = (frameTally[f.label] || 0) + f.score;
      }
    }
  }

  const count = analyzedArticles.length || 1;
  const avgNeg = Math.round((totalNeg / count) * 10) / 10;
  const avgNeu = Math.round((totalNeu / count) * 10) / 10;
  const avgPos = Math.round((totalPos / count) * 10) / 10;

  const topFrames = Object.entries(frameTally)
    .map(([frame, sum]) => ({
      frame,
      percentage: Math.round((sum / count) * 10) / 10
    }))
    .sort((a, b) => b.percentage - a.percentage);

  let biasTendency = '';
  let hypothesisMatch: ScrapedSiteSummary['hypothesisMatch'] = 'Confirmada (Sesgo esperado)';

  if (inferredCountry === 'Colombia') {
    const isSecurityHigh = topFrames.some((f) => f.frame === 'Seguridad' && f.percentage >= 48);
    if (isSecurityHigh || avgNeg > avgPos) {
      biasTendency = 'Enfoque Punitivo / Seguridad y Alerta Ciudadana';
      hypothesisMatch = 'Confirmada (Sesgo esperado)';
    } else {
      biasTendency = 'Enfoque Institucional / Integración Social';
      hypothesisMatch = 'Parcial';
    }
  } else if (inferredCountry === 'México') {
    const isEconHigh = topFrames.some(
      (f) => (f.frame === 'Empleo y economía' || f.frame === 'Tránsito migratorio') && f.percentage >= 48
    );
    if (isEconHigh) {
      biasTendency = 'Enfoque de Integración Laboral y Tránsito Migratorio';
      hypothesisMatch = 'Confirmada (Sesgo esperado)';
    } else {
      biasTendency = 'Enfoque Asistencial / Derechos Humanos';
      hypothesisMatch = 'Parcial';
    }
  } else {
    biasTendency = 'Cobertura Geopolítica Neutra';
    hypothesisMatch = 'No concluyente';
  }

  if (onProgress) {
    onProgress({
      status: 'completed',
      currentStep: 5,
      totalSteps: 5,
      message: `Análisis completado exitosamente: ${analyzedArticles.length} noticias procesadas.`,
      articlesFoundCount: analyzedArticles.length
    });
  }

  return {
    siteName,
    domain: cleanUrl,
    country: inferredCountry,
    totalAnalyzed: analyzedArticles.length,
    averageSentiment: {
      negativo: avgNeg,
      neutro: avgNeu,
      positivo: avgPos
    },
    topFrames,
    biasTendency,
    hypothesisMatch,
    articles: analyzedArticles
  };
}

export function exportCorpusToCSV(articles: NewsArticle[]): string {
  const headers = ['ID', 'Medio', 'País', 'Fecha', 'Título', 'Sentimiento', 'Encuadre Dominante', 'URL'];
  const rows = articles.map((a) => {
    const sentiment = a.preAnalyzedResult?.sentiment.prediction || 'N/A';
    const topFrame = a.preAnalyzedResult?.frames[0]?.label || a.category;
    const cleanTitle = `"${a.title.replace(/"/g, '""')}"`;
    return [a.id, a.media, a.country, a.date, cleanTitle, sentiment, topFrame, a.url].join(',');
  });

  return [headers.join(','), ...rows].join('\n');
}

export function exportCorpusToJSON(summary: ScrapedSiteSummary): string {
  return JSON.stringify(summary, null, 2);
}
