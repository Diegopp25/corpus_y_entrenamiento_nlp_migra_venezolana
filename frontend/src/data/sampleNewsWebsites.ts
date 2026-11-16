import type { NewsSitePreset } from '../types';

export const SAMPLE_NEWS_SITES: NewsSitePreset[] = [
  {
    id: 'semana',
    name: 'Revista Semana',
    domain: 'semana.com',
    country: 'Colombia',
    flag: '🇨🇴',
    category: 'Medio Digital',
    description: 'Medio colombiano autorizado para la extracción y análisis de noticias sobre migración venezolana.',
    logoText: 'SEMANA',
    accentColor: '#dc2626',
    articles: [
      {
        id: 'sem-01',
        title: 'Cobertura sobre migración venezolana y seguridad en ciudades colombianas',
        snippet: 'Ejemplo local de respaldo para la vista del extractor; el contenido real se obtiene al rastrear el sitio autorizado.',
        fullText: 'Las autoridades y medios de comunicación han seguido de cerca la dinámica migratoria venezolana en Colombia, con reportes sobre integración, seguridad y respuestas institucionales en distintas regiones del país.',
        author: 'Redacción Semana',
        date: '19 de junio de 2026',
        media: 'Revista Semana',
        country: 'Colombia',
        url: 'https://www.semana.com',
        category: 'Política migratoria'
      }
    ]
  },
  {
    id: 'milenio',
    name: 'Milenio',
    domain: 'milenio.com',
    country: 'México',
    flag: '🇲🇽',
    category: 'Medio Digital',
    description: 'Medio mexicano autorizado para la extracción y análisis de noticias sobre migración venezolana.',
    logoText: 'MILENIO',
    accentColor: '#1d4ed8',
    articles: [
      {
        id: 'mil-01',
        title: 'Reportes sobre movilidad y atención a migrantes venezolanos en México',
        snippet: 'Ejemplo local de respaldo para la vista del extractor; el contenido real se obtiene al rastrear el sitio autorizado.',
        fullText: 'La cobertura periodística en México ha documentado rutas, trámites y condiciones de la población migrante venezolana, así como debates sobre políticas públicas, empleo y atención humanitaria.',
        author: 'Redacción Milenio',
        date: '18 de junio de 2026',
        media: 'Milenio',
        country: 'México',
        url: 'https://www.milenio.com',
        category: 'Tránsito migratorio'
      }
    ]
  },
  {
    id: 'la-cronica',
    name: 'La Crónica',
    domain: 'cronica.com.mx',
    country: 'México',
    flag: '🇲🇽',
    category: 'Medio Digital',
    description: 'Medio mexicano (La Crónica de Hoy) autorizado para la extracción y análisis de noticias sobre migración venezolana.',
    logoText: 'LA CRÓNICA',
    accentColor: '#0f766e',
    articles: [
      {
        id: 'cro-01',
        title: 'Seguimiento informativo sobre la migración venezolana en territorio mexicano',
        snippet: 'Ejemplo local de respaldo para la vista del extractor; el contenido real se obtiene al rastrear el sitio autorizado.',
        fullText: 'Distintos medios en México, incluida La Crónica, han publicado notas sobre el tránsito, la estancia y los retos que enfrentan personas migrantes venezolanas en el país, desde la frontera sur hasta ciudades del norte.',
        author: 'Redacción La Crónica',
        date: '10 de junio de 2026',
        media: 'La Crónica',
        country: 'México',
        url: 'https://www.cronica.com.mx',
        category: 'Tránsito migratorio'
      }
    ]
  }
];

export const PRELOADED_EXAMPLES = [
  {
    id: 'ex-1',
    label: 'Oportunidades de trabajo (Del screenshot)',
    snippet: 'Los migrantes venezolanos llegan a la ciudad en busca de trabajo y oportunidades...',
    text: 'Los migrantes venezolanos llegan a la ciudad en busca de trabajo y oportunidades para sus familias.',
    source: 'Ejemplo Estándar (Imagen de Referencia)',
    expectedBias: 'México (Laboral) / Neutro'
  },
  {
    id: 'ex-2',
    label: 'Ola de inseguridad y control (Del screenshot)',
    snippet: 'La ola de inseguridad crece y los ciudadanos exigen más controles...',
    text: 'La ola de inseguridad crece y los ciudadanos exigen más controles migratorios en las fronteras y barrios periféricos.',
    source: 'Semana / El Tiempo (Colombia)',
    expectedBias: 'Colombia (Enfoque Punitivo / Seguridad)'
  },
  {
    id: 'ex-3',
    label: 'Jornadas de salud y PPT (Del screenshot)',
    snippet: 'El gobierno anunció nuevas jornadas de atención en salud...',
    text: 'El gobierno anunció nuevas jornadas de atención en salud y regularización de documentos para la población migrante.',
    source: 'Boletín Institucional / El Tiempo',
    expectedBias: 'Acceso a servicios / Política migratoria'
  },
  {
    id: 'ex-4',
    label: 'Industria maquiladora y mano de obra (México)',
    snippet: 'Empresarios en Monterrey absorben mano de obra calificada...',
    text: 'Empresarios de Monterrey y Ciudad Juárez destacan la inserción laboral y el aporte productivo de la mano de obra venezolana en el sector manufacturero y de servicios técnicos, mitigando el déficit de trabajadores.',
    source: 'El Universal / Reforma (México)',
    expectedBias: 'México (Enfoque Laboral / Económico)'
  },
  {
    id: 'ex-5',
    label: 'Célula criminal y operativos policiales (Colombia)',
    snippet: 'Operativo del Gaula desarticula banda transnacional...',
    text: 'La Policía Nacional capturó en Bogotá a seis presuntos integrantes de una banda criminal dedicada a extorsiones, homicidios y atracos violentos, disparando las alarmas de seguridad ciudadana en la zona.',
    source: 'Revista Semana (Colombia)',
    expectedBias: 'Colombia (Seguridad / Criminalidad)'
  }
];
