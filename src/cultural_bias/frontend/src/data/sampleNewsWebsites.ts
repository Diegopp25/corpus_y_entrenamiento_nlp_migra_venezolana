import type { NewsSitePreset } from '../types';

export const SAMPLE_NEWS_SITES: NewsSitePreset[] = [
  {
    id: 'el-tiempo',
    name: 'El Tiempo',
    domain: 'eltiempo.com',
    country: 'Colombia',
    flag: '🇨🇴',
    category: 'Prensa Escrita',
    description: 'Diario de mayor circulación en Colombia. Cobertura nacional con énfasis en políticas públicas, frontera y convivencia urbana.',
    logoText: 'EL TIEMPO',
    accentColor: '#1e40af',
    articles: [
      {
        id: 'et-01',
        title: 'Refuerzan operativos policiales en zonas comerciales por denuncias de inseguridad y control migratorio',
        snippet: 'Autoridades metropolitanas y la Policía desplegaron patrullajes conjuntos en puntos neurálgicos de la capital...',
        fullText: 'La ola de inseguridad crece y los ciudadanos exigen más controles migratorios en las fronteras y barrios periféricos. En un operativo conjunto entre la Policía Metropolitana y Migración Colombia, se identificaron varios casos de personas indocumentadas en zonas comerciales. Las autoridades señalaron que se mantendrá la presencia en calles para mitigar delitos de alto impacto como atracos y microtráfico.',
        author: 'Redacción Justicia',
        date: '14 de mayo de 2026',
        media: 'El Tiempo',
        country: 'Colombia',
        url: 'https://eltiempo.com/justicia/seguridad-control-migratorio-bogota',
        category: 'Seguridad'
      },
      {
        id: 'et-02',
        title: 'Balance del Estatuto Temporal de Protección: 2.8 millones de venezolanos regularizados en el país',
        snippet: 'Cancillería y Migración Colombia presentaron las cifras de integración al sistema financiero y de salud...',
        fullText: 'El gobierno anunció nuevas jornadas de atención en salud y regularización de documentos para la población migrante a través del Estatuto Temporal de Protección (PPT). Más de dos millones de ciudadanos venezolanos ya cuentan con acceso formal a la seguridad social, afiliación al sistema de salud pública y oportunidades para abrir cuentas bancarias en Colombia.',
        author: 'Redacción Política',
        date: '28 de abril de 2026',
        media: 'El Tiempo',
        country: 'Colombia',
        url: 'https://eltiempo.com/politica/balance-ppt-venezolanos-colombia',
        category: 'Política migratoria'
      },
      {
        id: 'et-03',
        title: 'Crisis humanitaria y saturación hospitalaria en Cúcuta por aumento de atenciones de urgencia',
        snippet: 'El Hospital Erasmo Meoz alerta sobre sobreocupación en salas de partos y atención a pacientes crónicos...',
        fullText: 'El acceso a servicios hospitalarios en la zona de frontera sigue enfrentando retos críticos. Representantes del Hospital Universitario Erasmo Meoz de Cúcuta informaron que la demanda de consultas médicas, partos y vacunación por parte de familias venezolanas supera la capacidad financiera asignada, requiriendo auxilio urgente de cooperación internacional.',
        author: 'Corresponsal Frontera',
        date: '02 de junio de 2026',
        media: 'El Tiempo',
        country: 'Colombia',
        url: 'https://eltiempo.com/colombia/cucuta/crisis-hospitalaria-frontera-venezuela',
        category: 'Acceso a servicios'
      }
    ]
  },
  {
    id: 'revista-semana',
    name: 'Revista Semana',
    domain: 'semana.com',
    country: 'Colombia',
    flag: '🇨🇴',
    category: 'Medio Digital',
    description: 'Medio de análisis político y judicial. Tiende a priorizar encuadres de seguridad ciudadana, crimen organizado y orden público.',
    logoText: 'SEMANA',
    accentColor: '#dc2626',
    articles: [
      {
        id: 'sem-01',
        title: 'Cae peligrosa célula del Tren de Aragua vinculada a extorsiones en el centro y sur de Bogotá',
        snippet: 'Agentes del Gaula desarticularon una red delictiva transnacional que amenazaba a comerciantes...',
        fullText: 'La Fiscalía y la Policía Nacional confirmaron la captura de ocho presuntos integrantes de la banda criminal venezolana El Tren de Aragua. De acuerdo con las investigaciones, los delincuentes extorsionaban a comerciantes locales bajo amenazas de muerte y estaban involucrados en disputas violentas por el control territorial de microtráfico en la capital.',
        author: 'Unidad Investigativa Semana',
        date: '19 de junio de 2026',
        media: 'Revista Semana',
        country: 'Colombia',
        url: 'https://semana.com/nacion/capturas-tren-de-aragua-bogota',
        category: 'Seguridad'
      },
      {
        id: 'sem-02',
        title: 'La alarma vecinal por robos y atracos dispara el debate sobre el control de fronteras en Colombia',
        snippet: 'Gremios de comerciantes piden endurecer los filtros en pasos fronterizos y deportar a reincidentes...',
        fullText: 'Comunidades barriales y asociaciones de comerciantes en Bogotá, Medellín y Cali han manifestado su profunda preocupación por el incremento de hurtos a mano armada y atracos callejeros. Líderes gremiales solicitaron una revisión estricta de los antecedentes penales y deportaciones inmediatas a quienes cometan delitos en el territorio nacional.',
        author: 'Sección Nación',
        date: '05 de mayo de 2026',
        media: 'Revista Semana',
        country: 'Colombia',
        url: 'https://semana.com/nacion/debate-seguridad-migracion-colombia',
        category: 'Seguridad'
      }
    ]
  },
  {
    id: 'el-espectador',
    name: 'El Espectador',
    domain: 'elespectador.com',
    country: 'Colombia',
    flag: '🇨🇴',
    category: 'Prensa Escrita',
    description: 'Diario centenario colombiano de línea editorial progresista. Enfoque frecuente en derechos humanos, integración social y testimonios.',
    logoText: 'EL ESPECTADOR',
    accentColor: '#059669',
    articles: [
      {
        id: 'ee-01',
        title: 'Combatir la xenofobia en las aulas: iniciativas comunitarias promueven la acogida de niños migrantes',
        snippet: 'Docentes en colegios públicos de Soacha y Cúcuta lideran programas pedagógicos contra la estigmatización...',
        fullText: 'Los migrantes venezolanos llegan a la ciudad en busca de trabajo y oportunidades para sus familias, pero a menudo se enfrentan a barreras de discriminación y estigmatización. En escuelas distritales, profesores y familias colombianas y venezolanas trabajan juntos en talleres de convivencia y cultura ciudadana para erradicar el rechazo y construir espacios de solidaridad.',
        author: 'Redacción Educación',
        date: '10 de julio de 2026',
        media: 'El Espectador',
        country: 'Colombia',
        url: 'https://elespectador.com/educacion/integracion-social-ninos-migrantes',
        category: 'Integración social'
      },
      {
        id: 'ee-02',
        title: 'El tapón del Darién: los testimonios de supervivencia en la selva más peligrosa del continente',
        snippet: 'Familias con niños relatan las dificultades de una travesía marcada por el lodo y la vulnerabilidad extrema...',
        fullText: 'El tránsito migratorio por el Darién no se detiene a pesar de las alertas climáticas y la presencia de actores armados ilegales. Organismos humanitarios como Médicos Sin Fronteras y ACNUR reiteran la urgencia de establecer corredores de paso seguro para proteger la vida de niños y mujeres embarazadas que cruzan hacia Centroamérica.',
        author: 'Sección Internacional',
        date: '22 de junio de 2026',
        media: 'El Espectador',
        country: 'Colombia',
        url: 'https://elespectador.com/investigacion/travesia-darien-migrantes',
        category: 'Tránsito migratorio'
      }
    ]
  },
  {
    id: 'el-universal-mx',
    name: 'El Universal',
    domain: 'eluniversal.com.mx',
    country: 'México',
    flag: '🇲🇽',
    category: 'Prensa Escrita',
    description: 'Decano de la prensa en México. Tiende a presentar la migración venezolana bajo marcos de movilidad internacional y dinamismo laboral.',
    logoText: 'EL UNIVERSAL',
    accentColor: '#ea580c',
    articles: [
      {
        id: 'eu-01',
        title: 'Sector industrial del norte de México absorbe fuerza laboral migrante venezolana para cubrir vacantes técnicas',
        snippet: 'Cámaras empresariales destacan la preparación técnica y el impacto positivo en la productividad manufacturera...',
        fullText: 'Empresarios en Monterrey, Ciudad Juárez y Tijuana han encontrado en la fuerza laboral venezolana un recurso calificado para subsanar el déficit de técnicos en industrias maquiladoras. Los trabajadores migrantes destacan por su compromiso y formación técnica, dinamizando la economía regional y facilitando su integración productiva formal con salarios competitivos.',
        author: 'Redacción Economía',
        date: '11 de junio de 2026',
        media: 'El Universal',
        country: 'México',
        url: 'https://eluniversal.com.mx/cartera/fuerza-laboral-migrante-industria-norte',
        category: 'Empleo y economía'
      },
      {
        id: 'eu-02',
        title: 'Miles de migrantes esperan resolución de citas CBP One en Tapachula antes de avanzar a la frontera norte',
        snippet: 'Albergues de la sociedad civil y COMAR coordinan ayuda humanitaria y permisos de estancia transitoria...',
        fullText: 'En Chiapas y Tapachula, miles de migrantes venezolanos en tránsito permanecen en albergues a la espera de autorizaciones electrónicas para ingresar ordenadamente a Estados Unidos. La Comisión Mexicana de Ayuda a Refugiados (COMAR) y el INM trabajan en esquemas de estadía temporal mientras se procesan las solicitudes de refugio internacional.',
        author: 'Corresponsal Chiapas',
        date: '04 de julio de 2026',
        media: 'El Universal',
        country: 'México',
        url: 'https://eluniversal.com.mx/estados/tapachula-espera-citas-migrantes',
        category: 'Tránsito migratorio'
      }
    ]
  },
  {
    id: 'milenio-mx',
    name: 'Milenio',
    domain: 'milenio.com',
    country: 'México',
    flag: '🇲🇽',
    category: 'Medio Digital',
    description: 'Uno de los portales de noticias digitales más leídos en México. Cobertura ágil de rutas fronterizas, economía y políticas migratorias.',
    logoText: 'MILENIO',
    accentColor: '#7c3aed',
    articles: [
      {
        id: 'mil-01',
        title: 'Emprendimientos gastronómicos y comercios fundados por venezolanos impulsan el consumo en CDMX y Guadalajara',
        snippet: 'Nuevos negocios dinamizan barrios urbanos y generan fuentes de empleo para ciudadanos mexicanos y extranjeros...',
        fullText: 'La inserción económica de la comunidad venezolana en grandes urbes mexicanas no se limita a empleos asalariados: decenas de emprendimientos de servicios, gastronomía y tecnología están generando empleo local e inyectando vitalidad al comercio barrial. Las asociaciones comerciales señalan que estos proyectos aportan ingresos fiscales y enriquecen la oferta cultural.',
        author: 'Negocios & Sociedad',
        date: '18 de junio de 2026',
        media: 'Milenio',
        country: 'México',
        url: 'https://milenio.com/negocios/emprendimientos-venezolanos-mexico',
        category: 'Empleo y economía'
      },
      {
        id: 'mil-02',
        title: 'México y EE.UU. afinan estrategia binacional para agilizar trámites laborales a migrantes sudamericanos',
        snippet: 'Cancillería mexicana plantea ampliar cupos de empleo temporal en obras estratégicas del sureste del país...',
        fullText: 'Representantes diplomáticos de México y Estados Unidos sostuvieron reuniones de trabajo para fortalecer las vías regulares de movilidad laboral. La propuesta busca canalizar a personas con experiencia en construcción y manufactura hacia proyectos de infraestructura estratégica en el sur de México, asegurando derechos laborales y visas humanitarias.',
        author: 'Política Internacional',
        date: '29 de mayo de 2026',
        media: 'Milenio',
        country: 'México',
        url: 'https://milenio.com/politica/acuerdo-laboral-migracion-mexico-eeuu',
        category: 'Política migratoria'
      }
    ]
  },
  {
    id: 'reforma-mx',
    name: 'Reforma',
    domain: 'reforma.com',
    country: 'México',
    flag: '🇲🇽',
    category: 'Prensa Escrita',
    description: 'Diario de referencia para la comunidad empresarial y política en México, enfocado en impacto macroeconómico y marcos regulatorios.',
    logoText: 'REFORMA',
    accentColor: '#0284c7',
    articles: [
      {
        id: 'ref-01',
        title: 'Estudio económico revela que regularización de migrantes aportaría hasta 0.4% al PIB en la región fronteriza',
        snippet: 'Investigadores del Colegio de la Frontera Norte destacan la capacidad tributaria y de consumo de las familias migrantes...',
        fullText: 'La integración laboral plena de la población venezolana asentada en estados fronterizos como Coahuila, Sonora y Nuevo León representa un impulso cuantitativo para la economía nacional. Investigadores señalan que dotar de permisos de trabajo definitivos fomenta el pago de impuestos, eleva la productividad de las pymes y dinamiza el mercado de vivienda.',
        author: 'Sección Negocios',
        date: '02 de julio de 2026',
        media: 'Reforma',
        country: 'México',
        url: 'https://reforma.com/negocios/estudio-aporte-pib-migracion',
        category: 'Empleo y economía'
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
