// Predetermined demo briefs. Each brief is pure data: the engine (../engine.js)
// turns the client's yes/no/why reactions into a master profile and channel pieces.
//
// Shape of a brief:
//   id, role, roleArticle ("un/a ..."), sector, brief (the vague original quote)
//   meta: zone, zoneConfirmed?, locFilter {default, confirmed?}, salaryCap,
//         summaryLead, postIntro, hashtags, expFilter {crit, must, else}, excludeIfBudget
//   crit[]: { id, label, base (0-100 starting weight), src (where the starting weight came from),
//             fromBrief (true if the client's brief explicitly asked for it),
//             tag (ATS tag), post (job-post line), q (screening-call question), form (yes/no form question),
//             bool (optional LinkedIn boolean group, used when the criterion is a must),
//             confirmedLabel / confirmedPost / confirmedForm (optional, used after the insight is confirmed) }
//   db[]: { id, label, ko (knockout phrasing), form (yes/no form question; "yes" disqualifies), not (optional boolean NOT clause) }
//   cards[6]: { letter, title, company, fields: [[k, v]...], yes: [reason], no: [reason] }
//       reason = { t: chip text, fx: { critId: +/-weight, db_x: 1 (flag a dealbreaker), n_x: 1 (count toward an insight) } }
//   insight: { counter (n_x key), threshold, text, why (for evidence), confirm: { crit, min, db } }
//   open[]: { t, unlessFlag?, unlessConfirmed?, ifLevel?: [critId, 1|2] }   // "Por confirmar con el cliente"
//   boolean: { titles, base }
//   github? : { query, extra: { critId: qualifier } }   // adds a GitHub channel (tech roles)

export const BRIEFS = [
  {
    id: 'ventas',
    role: 'Ejecutivo/a comercial B2B',
    roleArticle: 'un/a ejecutivo/a comercial B2B',
    sector: 'Distribuidora industrial',
    brief: 'Necesitamos un vendedor con experiencia, que hable inglés.',
    meta: {
      zone: 'Ciudad de Panamá', zoneConfirmed: 'Costa del Este',
      locFilter: { default: 'Ciudad de Panamá y alrededores', confirmed: 'Costa del Este, radio de 15 km (≈30 min)' },
      salaryCap: '$2,500',
      summaryLead: 'Busca a alguien que venda a empresas',
      postIntro: 'Empresa distribuidora busca ejecutivo/a para vender a empresas y crecer su cartera.',
      hashtags: '#Empleo #Panamá #VentasB2B',
      expFilter: { crit: 'exp', must: '5 años o más', else: '3 años o más' },
      excludeIfBudget: 'cargos de gerencia regional (aspiración fuera de rango)'
    },
    crit: [
      { id: 'b2b', label: 'Venta B2B (a empresas)', base: 45, src: 'Supuesto inicial del reclutador.', tag: 'B2B', lead: true,
        post: 'Experiencia vendiendo a empresas (B2B)', q: '¿A qué tipo de empresas le vende hoy? Pida dos clientes de ejemplo.', form: '¿Ha vendido a empresas (B2B) en los últimos 3 años?' },
      { id: 'exp', label: '5+ años en ventas', base: 25, src: 'Del brief: “con experiencia”, sin cifra.', fromBrief: true, tag: 'Ventas 5+ años',
        post: '5 años o más en ventas', q: '¿Cuántos años lleva en ventas y en qué puestos?', form: '¿Tiene 5 años o más en ventas?' },
      { id: 'cartera', label: 'Cartera de clientes propia', base: 0, tag: 'Cartera de clientes', bool: '("cartera de clientes" OR "manejo de cartera")',
        post: 'Cartera de clientes propia', q: '¿Cuántos clientes activos maneja y cuáles le seguirían?', form: '¿Maneja hoy una cartera de clientes propia?' },
      { id: 'sector', label: 'Industrial / venta técnica', base: 0, tag: 'Venta técnica', bool: '(industrial OR ferretería OR suministros OR "venta técnica")',
        post: 'Venta técnica o industrial', q: '¿Qué productos técnicos o industriales ha vendido? Pida un ejemplo.', form: '¿Ha vendido productos técnicos o industriales?' },
      { id: 'loc', label: 'Cerca de la oficina (Costa del Este)', base: 20, src: 'Supuesto: la oficina está en Costa del Este.', tag: 'Ciudad de Panamá',
        confirmedLabel: '30 min o menos de Costa del Este', confirmedPost: 'Residir a 30 min o menos de Costa del Este',
        post: 'Residir cerca de Costa del Este', q: '¿Dónde vive y cuánto tarda en llegar a Costa del Este?', form: '¿Vive a 30 min o menos de Costa del Este?' },
      { id: 'eng', label: 'Inglés intermedio o más', base: 35, src: 'Del brief: “que hable inglés”.', fromBrief: true, tag: 'Inglés', bool: '(inglés OR English OR bilingüe)',
        post: 'Inglés intermedio o superior', q: 'Haga dos preguntas en inglés. ¿Sostiene la conversación?', form: '¿Su nivel de inglés es intermedio o superior?' },
      { id: 'crm', label: 'Maneja un CRM', base: 0, tag: 'CRM', bool: '(CRM OR Salesforce OR HubSpot)',
        post: 'Manejo de CRM (Salesforce, HubSpot u otro)', q: '¿Qué CRM usa y para qué lo usa a diario?', form: '¿Usa un CRM en su trabajo actual?' }
    ],
    db: [
      { id: 'db_b2c', label: 'Solo experiencia a consumidor', ko: 'Solo ha vendido a consumidor final', form: '¿Ha vendido solamente a consumidor final?', not: '(retail OR tienda OR "punto de venta")' },
      { id: 'db_budget', label: 'Aspiración sobre $2,500', ko: 'Su aspiración supera $2,500', form: '¿Su aspiración salarial es mayor a $2,500?' },
      { id: 'db_far', label: 'Vive a más de 30 min', ko: 'Vive a más de 30 min de Costa del Este', form: '' }
    ],
    insight: {
      counter: 'n_area', threshold: 2, why: 'zona',
      text: 'Descartó 2 perfiles por ubicación. ¿Es requisito vivir a 30 min o menos de Costa del Este?',
      confirm: { crit: 'loc', min: 92, db: 'db_far' }
    },
    open: [
      { t: 'Rango salarial: ningún perfil se descartó por precio.', unlessFlag: 'db_budget' },
      { t: 'Ubicación: ¿importa dónde viva la persona?', unlessConfirmed: true },
      { t: 'Reubicación: ¿acepta a alguien dispuesto a mudarse?', unlessConfirmed: true },
      { t: 'Inglés: ¿requisito o deseable? El brief y las reacciones no coinciden.', ifLevel: ['eng', 1] },
      { t: 'Modalidad: ¿presencial, híbrido o en campo?' }
    ],
    boolean: {
      titles: '("ejecutivo de ventas" OR "ejecutiva de ventas" OR "ejecutivo de cuentas" OR "key account" OR "vendedor técnico")',
      base: '(B2B OR "venta corporativa" OR distribución)'
    },
    cards: [
      { letter: 'A', title: 'Ejecutiva de ventas', company: 'tienda de electrónica',
        fields: [['Experiencia', '2 años'], ['Sector', 'Retail (a consumidor)'], ['Zona', 'Bethania, Ciudad de Panamá'], ['Inglés', 'Básico'], ['Aspiración', '$1,200'], ['Cartera', 'No']],
        no: [{ t: 'Muy junior', fx: { exp: 25 } }, { t: 'Solo ha vendido a consumidor', fx: { b2b: 20, db_b2c: 1 } }, { t: 'Inglés muy básico', fx: { eng: 20 } }],
        yes: [{ t: 'Vive cerca', fx: { loc: 10 } }, { t: 'Puede aprender', fx: { exp: -10 } }] },
      { letter: 'B', title: 'Representante de ventas', company: 'distribuidora de consumo masivo',
        fields: [['Experiencia', '6 años'], ['Sector', 'Consumo masivo B2B'], ['Zona', 'David, Chiriquí'], ['Inglés', 'Intermedio'], ['Aspiración', '$1,800'], ['Cartera', 'Parcial']],
        no: [{ t: 'Vive fuera del área', fx: { loc: 15, n_area: 1 } }, { t: 'Consumo masivo, no industrial', fx: { sector: 30 } }, { t: 'Inglés insuficiente', fx: { eng: 20 } }],
        yes: [{ t: 'Experiencia B2B', fx: { b2b: 10 } }, { t: 'Buena trayectoria', fx: { exp: 10 } }] },
      { letter: 'C', title: 'Ejecutiva de cuentas clave', company: 'suministros industriales',
        fields: [['Experiencia', '5 años'], ['Sector', 'Industrial B2B'], ['Zona', 'Costa del Este'], ['Inglés', 'Avanzado'], ['Aspiración', '$2,000'], ['Cartera', '40 clientes']],
        yes: [{ t: 'Trae cartera propia', fx: { cartera: 40 } }, { t: 'Conoce el sector industrial', fx: { sector: 35 } }, { t: 'Inglés avanzado', fx: { eng: 15 } }, { t: 'Vive cerca', fx: { loc: 15 } }],
        no: [{ t: 'El inglés no hace falta', fx: { eng: -20 } }, { t: 'Demasiado senior', fx: { exp: -10 } }] },
      { letter: 'D', title: 'Gerente regional de ventas', company: 'agroquímicos',
        fields: [['Experiencia', '9 años'], ['Sector', 'Agro B2B'], ['Zona', 'Arraiján, Panamá Oeste'], ['Inglés', 'Avanzado'], ['Aspiración', '$3,500'], ['Cartera', 'Sí']],
        no: [{ t: 'Fuera de presupuesto', fx: { db_budget: 1 } }, { t: 'Vive fuera del área', fx: { loc: 15, n_area: 1 } }, { t: 'Sobrecalificado', fx: { exp: -5 } }],
        yes: [{ t: 'Liderazgo', fx: { exp: 10 } }, { t: 'Inglés avanzado', fx: { eng: 10 } }] },
      { letter: 'E', title: 'Vendedor técnico', company: 'distribución ferretera',
        fields: [['Experiencia', '4 años'], ['Sector', 'Ferretería B2B'], ['Zona', 'San Francisco'], ['Inglés', 'Intermedio'], ['Aspiración', '$1,900'], ['Herramientas', 'Salesforce']],
        yes: [{ t: 'Trae cartera propia', fx: { cartera: 35 } }, { t: 'Domina un CRM', fx: { crm: 40 } }, { t: 'Venta técnica', fx: { sector: 30 } }],
        no: [{ t: 'Poca experiencia', fx: { exp: 15 } }, { t: 'Inglés insuficiente', fx: { eng: 15 } }] },
      { letter: 'F', title: 'Ejecutivo comercial', company: 'materiales de construcción',
        fields: [['Experiencia', '7 años'], ['Sector', 'Construcción B2B'], ['Zona', 'La Chorrera'], ['Inglés', 'Básico'], ['Aspiración', '$1,900'], ['Cartera', 'No']],
        no: [{ t: 'Vive fuera del área', fx: { loc: 15, n_area: 1 } }, { t: 'Sin cartera propia', fx: { cartera: 20 } }, { t: 'Inglés insuficiente', fx: { eng: 15 } }],
        yes: [{ t: 'Sector correcto', fx: { sector: 20 } }, { t: 'Experiencia sólida', fx: { exp: 10 } }] }
    ]
  },

  {
    id: 'contador',
    role: 'Contador/a senior',
    roleArticle: 'un/a contador/a senior',
    sector: 'Grupo comercial',
    brief: 'Necesitamos un contador con experiencia que sepa de impuestos.',
    meta: {
      zone: 'Ciudad de Panamá (Obarrio)',
      locFilter: { default: 'Ciudad de Panamá y alrededores' },
      salaryCap: '$2,800',
      summaryLead: 'Busca a alguien que lleve la contabilidad y los impuestos de la empresa',
      postIntro: 'Grupo comercial busca contador/a para llevar contabilidad, cierres e impuestos.',
      hashtags: '#Empleo #Panamá #Contabilidad',
      expFilter: { crit: 'exp', must: '5 años o más', else: '3 años o más' },
      excludeIfBudget: 'gerencias financieras y socios de firma (aspiración fuera de rango)'
    },
    crit: [
      { id: 'tax', label: 'Impuestos: DGI, ITBMS y renta', base: 40, src: 'Del brief: “que sepa de impuestos”.', fromBrief: true, tag: 'Impuestos', lead: true, bool: '(impuestos OR DGI OR ITBMS OR tributario)',
        post: 'Manejo de impuestos: declaraciones de ITBMS y renta ante la DGI', q: '¿Qué declaraciones prepara hoy y con qué frecuencia?', form: '¿Prepara declaraciones de ITBMS o renta actualmente?' },
      { id: 'exp', label: '5+ años en contabilidad', base: 30, src: 'Del brief: “con experiencia”, sin cifra.', fromBrief: true, tag: 'Contabilidad 5+ años',
        post: '5 años o más en contabilidad', q: '¿Cuántos años lleva en contabilidad y llevando qué tipo de empresas?', form: '¿Tiene 5 años o más en contabilidad?' },
      { id: 'cpa', label: 'Idoneidad de CPA', base: 30, src: 'Supuesto del reclutador.', tag: 'CPA', bool: '("contador público autorizado" OR CPA OR idoneidad)',
        confirmedLabel: 'Idoneidad de CPA vigente', confirmedPost: 'Idoneidad de Contador Público Autorizado vigente',
        post: 'Idoneidad de Contador Público Autorizado', q: '¿Tiene idoneidad de CPA vigente? Pida el número.', form: '¿Tiene idoneidad de CPA vigente?' },
      { id: 'niif', label: 'NIIF y estados financieros', base: 15, tag: 'NIIF', bool: '(NIIF OR IFRS)',
        post: 'Cierres y estados financieros bajo NIIF', q: '¿Ha preparado estados financieros bajo NIIF? ¿Para quién?', form: '¿Ha preparado estados financieros bajo NIIF?' },
      { id: 'erp', label: 'SAP Business One u otro ERP', base: 0, tag: 'ERP', bool: '("SAP Business One" OR SAP OR ERP)',
        post: 'Manejo de ERP (SAP Business One u otro)', q: '¿Qué ERP usa y qué módulos maneja?', form: '¿Usa un ERP en su trabajo actual?' },
      { id: 'payroll', label: 'Planilla y CSS', base: 0, tag: 'Planilla', bool: '(planilla OR nómina OR CSS)',
        post: 'Planilla y cuotas de la CSS', q: '¿Ha manejado planilla y pagos a la CSS?', form: '¿Ha manejado planilla y CSS?' },
      { id: 'eng', label: 'Inglés intermedio', base: 0, tag: 'Inglés', bool: '(inglés OR English)',
        post: 'Inglés intermedio', q: '¿Ha reportado a casa matriz o auditores en inglés?', form: '¿Su inglés es intermedio o superior?' }
    ],
    db: [
      { id: 'db_nocpa', label: 'Sin idoneidad de CPA', ko: 'No tiene idoneidad de CPA vigente', form: '' },
      { id: 'db_budget', label: 'Aspiración sobre $2,800', ko: 'Su aspiración supera $2,800', form: '¿Su aspiración salarial es mayor a $2,800?' },
      { id: 'db_audit', label: 'Solo auditoría externa', ko: 'Solo ha hecho auditoría externa, sin llevar operación', form: '¿Su experiencia es solamente en auditoría externa?', not: '("auditor externo")' }
    ],
    insight: {
      counter: 'n_cpa', threshold: 2, why: 'falta de idoneidad',
      text: 'Descartó 2 perfiles por no tener idoneidad. ¿Es requisito tener idoneidad de CPA?',
      confirm: { crit: 'cpa', min: 95, db: 'db_nocpa' }
    },
    open: [
      { t: 'Rango salarial: ningún perfil se descartó por precio.', unlessFlag: 'db_budget' },
      { t: 'Idoneidad: ¿es requisito o puede estar en trámite?', unlessConfirmed: true },
      { t: '¿A cuántas empresas o razones sociales les llevaría contabilidad?' },
      { t: 'Modalidad: ¿presencial o híbrido?' }
    ],
    boolean: {
      titles: '(contador OR contadora OR "contador público" OR "contador general")',
      base: '(impuestos OR DGI OR ITBMS OR tributario)'
    },
    cards: [
      { letter: 'A', title: 'Asistente contable', company: 'firma contable pequeña',
        fields: [['Experiencia', '2 años'], ['Idoneidad', 'No'], ['Impuestos', 'Apoya en ITBMS'], ['Sistemas', 'Excel, QuickBooks'], ['Inglés', 'Básico'], ['Aspiración', '$900']],
        no: [{ t: 'Muy junior', fx: { exp: 25 } }, { t: 'Sin idoneidad', fx: { cpa: 15, n_cpa: 1 } }, { t: 'No declara impuestos por su cuenta', fx: { tax: 20 } }],
        yes: [{ t: 'Buena base para formar', fx: { exp: -10 } }] },
      { letter: 'B', title: 'Contador', company: 'constructora',
        fields: [['Experiencia', '6 años'], ['Idoneidad', 'Sí'], ['Impuestos', 'ITBMS y renta'], ['Sistemas', 'SAP Business One'], ['Inglés', 'Básico'], ['Aspiración', '$2,000']],
        yes: [{ t: 'Usa un ERP', fx: { erp: 35 } }, { t: 'Maneja planilla y CSS', fx: { payroll: 30 } }, { t: 'Tiene idoneidad', fx: { cpa: 20 } }],
        no: [{ t: 'Inglés básico', fx: { eng: 20 } }, { t: 'Sector muy distinto', fx: {} }] },
      { letter: 'C', title: 'Auditora senior', company: 'firma de auditoría internacional',
        fields: [['Experiencia', '7 años'], ['Idoneidad', 'Sí'], ['Impuestos', 'Revisión, no preparación'], ['Normas', 'NIIF'], ['Inglés', 'Avanzado'], ['Aspiración', '$3,200']],
        no: [{ t: 'Fuera de presupuesto', fx: { db_budget: 1 } }, { t: 'Solo auditoría, no operación', fx: { db_audit: 1, tax: 10 } }, { t: 'Sobrecalificada', fx: { exp: -5 } }],
        yes: [{ t: 'NIIF sólido', fx: { niif: 35 } }, { t: 'Inglés avanzado', fx: { eng: 25 } }] },
      { letter: 'D', title: 'Contador general', company: 'distribuidora',
        fields: [['Experiencia', '5 años'], ['Idoneidad', 'En trámite'], ['Impuestos', 'ITBMS y renta'], ['Sistemas', 'Excel'], ['Inglés', 'Básico'], ['Aspiración', '$1,600']],
        no: [{ t: 'Sin idoneidad', fx: { cpa: 15, n_cpa: 1 } }, { t: 'No usa ERP', fx: { erp: 20 } }],
        yes: [{ t: 'Domina ITBMS y renta', fx: { tax: 25 } }, { t: 'Conoce distribución', fx: {} }] },
      { letter: 'E', title: 'Contadora', company: 'grupo hotelero',
        fields: [['Experiencia', '8 años'], ['Idoneidad', 'Sí'], ['Impuestos', 'ITBMS, renta, municipio'], ['Sistemas', 'SAP Business One'], ['Normas', 'NIIF'], ['Aspiración', '$2,500']],
        yes: [{ t: 'Impuestos al día', fx: { tax: 20 } }, { t: 'Cierres bajo NIIF', fx: { niif: 25 } }, { t: 'Usa SAP B1', fx: { erp: 25 } }],
        no: [{ t: 'Demasiado senior', fx: { exp: -10 } }, { t: 'Busco algo más junior', fx: { exp: -15 } }] },
      { letter: 'F', title: 'Contador independiente', company: 'pymes, por servicios',
        fields: [['Experiencia', '4 años'], ['Idoneidad', 'No'], ['Impuestos', 'Declara ITBMS'], ['Sistemas', 'Excel'], ['Inglés', 'Básico'], ['Aspiración', '$1,400']],
        no: [{ t: 'Sin idoneidad', fx: { cpa: 15, n_cpa: 1 } }, { t: 'Solo independiente', fx: { exp: 10 } }, { t: 'Poca experiencia', fx: { exp: 15 } }],
        yes: [{ t: 'Conoce pymes', fx: {} }, { t: 'Declara ITBMS', fx: { tax: 15 } }] }
    ]
  },

  {
    id: 'bodega',
    role: 'Supervisor/a de bodega',
    roleArticle: 'un/a supervisor/a de bodega',
    sector: 'Operador logístico, Zona Libre',
    brief: 'Busco un supervisor de bodega responsable.',
    meta: {
      zone: 'Zona Libre de Colón',
      locFilter: { default: 'Colón, Sabanitas y alrededores' },
      salaryCap: '$1,600',
      summaryLead: 'Busca a alguien que dirija la operación de bodega',
      postIntro: 'Operador logístico en la Zona Libre de Colón busca supervisor/a para dirigir su bodega.',
      hashtags: '#Empleo #Colón #Logística',
      expFilter: { crit: 'exp', must: '3 años o más', else: '2 años o más' },
      excludeIfBudget: 'gerencias de operaciones (aspiración fuera de rango)'
    },
    crit: [
      { id: 'team', label: 'Ha liderado equipos de 10+', base: 25, src: 'Del brief: “responsable”, sin detalle.', fromBrief: true, tag: 'Supervisión', lead: true, bool: '(supervisión OR "a cargo de" OR "personal a cargo")',
        post: 'Experiencia supervisando equipos de 10 personas o más', q: '¿Cuántas personas ha tenido a cargo y en qué turnos?', form: '¿Ha supervisado equipos de 10 personas o más?' },
      { id: 'exp', label: '3+ años en bodega', base: 30, src: 'Supuesto del reclutador.', tag: 'Bodega 3+ años',
        post: '3 años o más en operación de bodega', q: '¿Cuántos años lleva en bodega y en qué tipo de mercancía?', form: '¿Tiene 3 años o más en bodega?' },
      { id: 'inv', label: 'Conteos e inventario cíclico', base: 30, src: 'Supuesto del reclutador.', tag: 'Inventario', bool: '("inventario cíclico" OR conteos OR inventarios)',
        post: 'Conteos e inventario cíclico', q: '¿Cómo organiza un conteo cíclico y qué hace con las diferencias?', form: '¿Ha dirigido conteos de inventario?' },
      { id: 'shift', label: 'Turnos rotativos', base: 15, tag: 'Turnos rotativos',
        confirmedLabel: 'Turnos rotativos, incluso nocturnos', confirmedPost: 'Disponibilidad para turnos rotativos, incluidos nocturnos',
        post: 'Disponibilidad para turnos rotativos', q: '¿Puede trabajar turnos rotativos, incluidos los nocturnos?', form: '¿Puede trabajar turnos rotativos?' },
      { id: 'wms', label: 'Sistema de inventario (WMS)', base: 20, tag: 'WMS', bool: '(WMS OR "SAP WM" OR "sistema de inventario")',
        post: 'Manejo de un WMS o sistema de inventario', q: '¿Qué sistema de inventario usa y para qué?', form: '¿Usa un WMS o sistema de inventario?' },
      { id: 'loc', label: 'Vive en Colón o cerca', base: 10, tag: 'Colón',
        post: 'Residir en Colón o alrededores', q: '¿Dónde vive y cuánto tarda en llegar a la Zona Libre?', form: '¿Vive en Colón o alrededores?' },
      { id: 'forklift', label: 'Certificación de montacargas', base: 0, tag: 'Montacargas', bool: '(montacargas)',
        post: 'Certificación de montacargas', q: '¿Tiene certificación de montacargas vigente?', form: '¿Tiene certificación de montacargas?' },
      { id: 'eng', label: 'Inglés básico para documentos', base: 0, tag: 'Inglés básico',
        post: 'Inglés básico para leer documentos de embarque', q: '¿Puede leer un packing list en inglés?', form: '¿Lee documentos de embarque en inglés?' }
    ],
    db: [
      { id: 'db_noshift', label: 'No hace turnos nocturnos', ko: 'No puede trabajar turnos nocturnos', form: '' },
      { id: 'db_budget', label: 'Aspiración sobre $1,600', ko: 'Su aspiración supera $1,600', form: '¿Su aspiración salarial es mayor a $1,600?' }
    ],
    insight: {
      counter: 'n_shift', threshold: 2, why: 'turnos',
      text: 'Descartó 2 perfiles por trabajar solo de día. ¿Es requisito hacer turnos rotativos, incluso nocturnos?',
      confirm: { crit: 'shift', min: 92, db: 'db_noshift' }
    },
    open: [
      { t: 'Rango salarial: ningún perfil se descartó por precio.', unlessFlag: 'db_budget' },
      { t: 'Turnos: ¿son obligatorios los nocturnos?', unlessConfirmed: true },
      { t: '¿Ofrecen transporte desde la ciudad? Cambia a quién se puede buscar.' },
      { t: '¿Qué tipo de mercancía maneja la bodega?' }
    ],
    boolean: {
      titles: '("supervisor de bodega" OR "jefe de almacén" OR "supervisor de almacén" OR "supervisor de turno")',
      base: '(bodega OR almacén OR inventario OR logística)'
    },
    cards: [
      { letter: 'A', title: 'Auxiliar de bodega', company: 'ferretería',
        fields: [['Experiencia', '2 años'], ['Equipo a cargo', 'Ninguno'], ['Zona', 'Ciudad de Panamá'], ['Turnos', 'Solo de día'], ['Sistema', 'Excel'], ['Aspiración', '$750']],
        no: [{ t: 'Nunca ha liderado', fx: { team: 30 } }, { t: 'Solo turno de día', fx: { shift: 15, n_shift: 1 } }, { t: 'Vive lejos de Colón', fx: { loc: 20 } }],
        yes: [{ t: 'Conoce inventario', fx: { inv: 10 } }] },
      { letter: 'B', title: 'Jefe de almacén', company: 'cadena de retail nacional',
        fields: [['Experiencia', '9 años'], ['Equipo a cargo', '25 personas'], ['Zona', 'Colón'], ['Turnos', 'Rotativos'], ['Sistema', 'SAP WM'], ['Aspiración', '$2,200']],
        no: [{ t: 'Fuera de presupuesto', fx: { db_budget: 1 } }, { t: 'Sobrecalificado', fx: { exp: -5 } }],
        yes: [{ t: 'Lideró un equipo grande', fx: { team: 30 } }, { t: 'Usa un WMS', fx: { wms: 30 } }, { t: 'Vive en Colón', fx: { loc: 25 } }] },
      { letter: 'C', title: 'Supervisora de turno', company: 'operador logístico en Zona Libre',
        fields: [['Experiencia', '5 años'], ['Equipo a cargo', '12 personas'], ['Zona', 'Colón'], ['Turnos', 'Rotativos'], ['Sistema', 'WMS propio'], ['Aspiración', '$1,400']],
        yes: [{ t: 'Conoce la Zona Libre', fx: { loc: 15, exp: 10 } }, { t: 'Hace turnos rotativos', fx: { shift: 25 } }, { t: 'Lidera 12 personas', fx: { team: 25 } }],
        no: [{ t: 'Poco inglés', fx: { eng: 20 } }] },
      { letter: 'D', title: 'Coordinador de inventario', company: 'distribuidora farmacéutica',
        fields: [['Experiencia', '4 años'], ['Equipo a cargo', '4 personas'], ['Zona', 'Arraiján'], ['Turnos', 'Solo de día'], ['Fuerte en', 'Conteos cíclicos'], ['Aspiración', '$1,300']],
        no: [{ t: 'Solo turno de día', fx: { shift: 15, n_shift: 1 } }, { t: 'Equipo muy pequeño', fx: { team: 20 } }, { t: 'Vive lejos', fx: { loc: 15 } }],
        yes: [{ t: 'Fuerte en conteos', fx: { inv: 30 } }] },
      { letter: 'E', title: 'Supervisor de bodega', company: 'importadora',
        fields: [['Experiencia', '6 años'], ['Equipo a cargo', '15 personas'], ['Zona', 'Sabanitas, Colón'], ['Turnos', 'Rotativos'], ['Certificación', 'Montacargas'], ['Aspiración', '$1,500']],
        yes: [{ t: 'Certificado de montacargas', fx: { forklift: 35 } }, { t: 'Vive cerca', fx: { loc: 20 } }, { t: 'Lee documentos en inglés', fx: { eng: 25 } }],
        no: [{ t: 'No usa WMS', fx: { wms: 15 } }] },
      { letter: 'F', title: 'Encargado de despacho', company: 'cadena de supermercados',
        fields: [['Experiencia', '7 años'], ['Equipo a cargo', '8 personas'], ['Zona', 'La Chorrera'], ['Turnos', 'Solo de día'], ['Sistema', 'Excel'], ['Aspiración', '$1,350']],
        no: [{ t: 'Solo turno de día', fx: { shift: 15, n_shift: 1 } }, { t: 'Vive lejos', fx: { loc: 15 } }],
        yes: [{ t: 'Experiencia en despacho', fx: { exp: 10 } }] }
    ]
  },

  {
    id: 'dev',
    role: 'Desarrollador/a full-stack',
    roleArticle: 'un/a desarrollador/a full-stack',
    sector: 'Empresa de software',
    brief: 'Necesitamos un programador que sepa de todo.',
    meta: {
      zone: 'Ciudad de Panamá (híbrido)',
      locFilter: { default: 'Panamá, remoto o híbrido' },
      salaryCap: '$4,000',
      summaryLead: 'Busca a alguien que construya producto web de punta a punta',
      postIntro: 'Empresa de software busca desarrollador/a full-stack para construir y mantener su producto web.',
      hashtags: '#Empleo #Panamá #Tecnología',
      expFilter: { crit: 'exp', must: '4 años o más', else: '2 años o más' },
      excludeIfBudget: 'perfiles staff/principal en empresas de EE. UU. (aspiración fuera de rango)'
    },
    crit: [
      { id: 'ts', label: 'TypeScript / Node.js', base: 30, src: 'Del brief: “que sepa de todo” (supuesto: web full-stack).', fromBrief: true, tag: 'TypeScript', lead: true,
        post: 'TypeScript y Node.js en producción', q: '¿Qué ha construido con TypeScript y Node? Pida un ejemplo concreto.', form: '¿Usa TypeScript y Node.js en su trabajo actual?' },
      { id: 'react', label: 'React', base: 30, src: 'Del brief: “que sepa de todo” (supuesto: web full-stack).', fromBrief: true, tag: 'React', bool: '(React OR Next.js)',
        post: 'React (o Next.js)', q: '¿Cuánto frontend hace hoy y con qué stack?', form: '¿Trabaja con React actualmente?' },
      { id: 'exp', label: '4+ años programando', base: 25, src: 'Supuesto del reclutador.', tag: '4+ años',
        post: '4 años o más programando profesionalmente', q: '¿Cuántos años lleva programando profesionalmente y en qué equipos?', form: '¿Tiene 4 años o más de experiencia profesional?' },
      { id: 'eng', label: 'Inglés avanzado', base: 20, tag: 'Inglés', bool: '(English OR inglés)',
        confirmedLabel: 'Inglés avanzado para llamadas con clientes', confirmedPost: 'Inglés avanzado: llamadas diarias con clientes en EE. UU.',
        post: 'Inglés avanzado', q: 'Haga la mitad de la llamada en inglés. ¿Explica una decisión técnica con claridad?', form: '¿Su inglés es avanzado?' },
      { id: 'prod', label: 'Ha mantenido sistemas en producción', base: 0, tag: 'Producción',
        post: 'Experiencia manteniendo sistemas en producción', q: 'Cuénteme de un incidente en producción que le tocó resolver.', form: '¿Ha mantenido un sistema en producción con usuarios reales?' },
      { id: 'cloud', label: 'Nube (AWS u otra)', base: 0, tag: 'AWS', bool: '(AWS OR GCP OR Azure)',
        post: 'Experiencia en nube (AWS, GCP o Azure)', q: '¿Qué servicios de nube ha configurado usted mismo?', form: '¿Ha trabajado con AWS, GCP o Azure?' },
      { id: 'fintech', label: 'Fintech o pagos', base: 0, tag: 'Fintech', bool: '(fintech OR pagos OR payments)',
        post: 'Experiencia en fintech o pagos', q: '¿Ha trabajado con pagos, conciliación o datos financieros?', form: '¿Ha trabajado en fintech o con pagos?' }
    ],
    db: [
      { id: 'db_eng', label: 'Sin inglés conversacional', ko: 'No sostiene una conversación técnica en inglés', form: '' },
      { id: 'db_budget', label: 'Aspiración sobre $4,000', ko: 'Su aspiración supera $4,000', form: '¿Su aspiración salarial es mayor a $4,000?' },
      { id: 'db_wp', label: 'Solo WordPress o no-code', ko: 'Solo ha trabajado con WordPress o herramientas no-code', form: '¿Su experiencia es solo con WordPress o no-code?', not: '(WordPress)' }
    ],
    insight: {
      counter: 'n_eng', threshold: 2, why: 'inglés',
      text: 'Descartó 2 perfiles por el inglés. ¿Es requisito inglés avanzado para hablar con clientes?',
      confirm: { crit: 'eng', min: 92, db: 'db_eng' }
    },
    open: [
      { t: 'Rango salarial: ningún perfil se descartó por precio.', unlessFlag: 'db_budget' },
      { t: '¿“Sabe de todo” incluye móvil, datos o DevOps? Las reacciones no lo dicen.' },
      { t: 'Inglés: ¿para leer documentación o para hablar con clientes?', unlessConfirmed: true },
      { t: '¿Remoto total, o cuántos días en oficina?' }
    ],
    boolean: {
      titles: '("full stack" OR fullstack OR "desarrollador web" OR "software engineer")',
      base: '(TypeScript OR JavaScript OR Node.js)'
    },
    github: {
      query: 'location:Panama language:TypeScript',
      extra: { react: 'topic:react', cloud: 'topic:aws', fintech: 'topic:payments' }
    },
    cards: [
      { letter: 'A', title: 'Desarrolladora web', company: 'agencia de marketing',
        fields: [['Experiencia', '2 años'], ['Stack', 'WordPress, PHP'], ['Producción', 'Sitios de clientes'], ['Inglés', 'Intermedio'], ['Modalidad', 'Presencial'], ['Aspiración', '$1,200']],
        no: [{ t: 'Solo WordPress', fx: { db_wp: 1, ts: 15 } }, { t: 'Muy junior', fx: { exp: 25 } }],
        yes: [{ t: 'Entrega rápido', fx: {} }] },
      { letter: 'B', title: 'Ingeniero de software', company: 'banco local',
        fields: [['Experiencia', '6 años'], ['Stack', 'Java, Angular'], ['Producción', 'Banca en línea'], ['Inglés', 'Básico'], ['Modalidad', 'Presencial'], ['Aspiración', '$2,800']],
        no: [{ t: 'Inglés insuficiente', fx: { eng: 15, n_eng: 1 } }, { t: 'Stack distinto', fx: { react: 15, ts: 10 } }],
        yes: [{ t: 'Experiencia en banca', fx: { fintech: 30 } }, { t: 'Mantiene sistemas en producción', fx: { prod: 30 } }] },
      { letter: 'C', title: 'Full-stack senior', company: 'startup de EE. UU., remoto',
        fields: [['Experiencia', '8 años'], ['Stack', 'TypeScript, React, Node'], ['Nube', 'AWS'], ['Inglés', 'Avanzado'], ['Modalidad', 'Remoto'], ['Aspiración', '$5,500']],
        no: [{ t: 'Fuera de presupuesto', fx: { db_budget: 1 } }],
        yes: [{ t: 'Stack exacto', fx: { ts: 20, react: 20 } }, { t: 'Maneja AWS', fx: { cloud: 35 } }, { t: 'Inglés avanzado', fx: { eng: 15 } }] },
      { letter: 'D', title: 'Desarrollador full-stack', company: 'fintech regional',
        fields: [['Experiencia', '4 años'], ['Stack', 'TypeScript, React, Node'], ['Dominio', 'Pagos'], ['Inglés', 'Intermedio bajo'], ['Modalidad', 'Híbrido'], ['Aspiración', '$3,000']],
        yes: [{ t: 'Experiencia en pagos', fx: { fintech: 35 } }, { t: 'Stack correcto', fx: { ts: 15, react: 15 } }],
        no: [{ t: 'Inglés insuficiente', fx: { eng: 15, n_eng: 1 } }] },
      { letter: 'E', title: 'Desarrolladora backend', company: 'e-commerce',
        fields: [['Experiencia', '5 años'], ['Stack', 'Node, PostgreSQL'], ['Nube', 'GCP'], ['Inglés', 'Avanzado'], ['Modalidad', 'Remoto'], ['Aspiración', '$3,400']],
        yes: [{ t: 'Mantiene sistemas en producción', fx: { prod: 35 } }, { t: 'Sabe de nube', fx: { cloud: 25 } }],
        no: [{ t: 'Poco frontend', fx: { react: 20 } }] },
      { letter: 'F', title: 'Desarrollador móvil', company: 'app de delivery',
        fields: [['Experiencia', '3 años'], ['Stack', 'React Native'], ['Producción', 'App con usuarios'], ['Inglés', 'Básico'], ['Modalidad', 'Presencial'], ['Aspiración', '$2,200']],
        no: [{ t: 'Inglés insuficiente', fx: { eng: 15, n_eng: 1 } }, { t: 'Solo móvil', fx: { react: 10 } }],
        yes: [{ t: 'Producto con usuarios reales', fx: { prod: 20 } }] }
    ]
  },

  {
    id: 'marketing',
    role: 'Coordinador/a de marketing',
    roleArticle: 'un/a coordinador/a de marketing',
    sector: 'Empresa de servicios B2B',
    brief: 'Alguien de marketing que maneje redes.',
    meta: {
      zone: 'Ciudad de Panamá',
      locFilter: { default: 'Ciudad de Panamá y alrededores' },
      salaryCap: '$2,200',
      summaryLead: 'Busca a alguien que genere demanda y mida resultados',
      postIntro: 'Empresa de servicios busca coordinador/a de marketing para generar demanda y medir resultados.',
      hashtags: '#Empleo #Panamá #Marketing',
      expFilter: { crit: 'exp', must: '3 años o más', else: '2 años o más' },
      excludeIfBudget: 'gerencias de marketing (aspiración fuera de rango)'
    },
    crit: [
      { id: 'social', label: 'Redes sociales', base: 45, src: 'Del brief: “que maneje redes”.', fromBrief: true, tag: 'Redes sociales', bool: '("redes sociales" OR "social media")',
        post: 'Manejo de redes sociales de marca', q: '¿Qué cuentas maneja hoy y qué resultado le pidieron?', form: '¿Maneja hoy redes sociales de una marca?' },
      { id: 'paid', label: 'Pauta pagada (Meta / Google Ads)', base: 10, tag: 'Pauta digital', bool: '("Meta Ads" OR "Google Ads" OR pauta OR "paid media")',
        confirmedLabel: 'Pauta y resultados, no solo publicaciones', confirmedPost: 'Manejo de pauta pagada con metas de resultados (leads, ventas)',
        post: 'Pauta pagada en Meta Ads o Google Ads', q: '¿Cuánto presupuesto mensual de pauta ha manejado y con qué resultado?', form: '¿Ha manejado pauta pagada en Meta o Google?' },
      { id: 'analytics', label: 'Mide resultados (GA4, reportes)', base: 0, tag: 'Analítica', bool: '(GA4 OR "Google Analytics" OR analítica)',
        post: 'Medición de resultados (GA4, reportes)', q: '¿Qué métricas reporta y a quién?', form: '¿Reporta métricas de resultados con GA4 u otra herramienta?' },
      { id: 'content', label: 'Produce contenido propio', base: 20, src: 'Supuesto: quien maneja redes produce contenido.', tag: 'Contenido', bool: '(contenido OR video)',
        post: 'Producción de contenido propio', q: 'Muéstreme tres piezas que haya hecho usted.', form: '¿Produce contenido propio (texto, foto, video)?' },
      { id: 'b2b', label: 'Marketing B2B', base: 0, tag: 'B2B', bool: '(B2B OR LinkedIn)',
        post: 'Marketing B2B (empresas como clientes)', q: '¿Ha hecho marketing para vender a empresas? ¿Cómo generaba leads?', form: '¿Ha hecho marketing B2B?' },
      { id: 'events', label: 'Organiza eventos', base: 0, tag: 'Eventos', bool: '(eventos OR webinars)',
        post: 'Organización de eventos y webinars', q: '¿Qué eventos ha organizado y cuántos asistentes tuvieron?', form: '¿Ha organizado eventos o webinars?' },
      { id: 'exp', label: '3+ años en marketing', base: 25, src: 'Supuesto del reclutador.', tag: 'Marketing 3+ años',
        post: '3 años o más en marketing', q: '¿Cuántos años lleva en marketing y en qué tipo de empresas?', form: '¿Tiene 3 años o más en marketing?' }
    ],
    db: [
      { id: 'db_cm', label: 'Solo publica, no mide', ko: 'Solo ha hecho community management, sin pauta ni resultados', form: '', not: '("community manager")' },
      { id: 'db_budget', label: 'Aspiración sobre $2,200', ko: 'Su aspiración supera $2,200', form: '¿Su aspiración salarial es mayor a $2,200?' }
    ],
    insight: {
      counter: 'n_cm', threshold: 2, why: 'solo publicar sin medir',
      text: 'Descartó 2 perfiles porque solo publican. ¿Busca a alguien que maneje pauta y resultados, no solo redes?',
      confirm: { crit: 'paid', min: 92, db: 'db_cm' }
    },
    open: [
      { t: 'Rango salarial: ningún perfil se descartó por precio.', unlessFlag: 'db_budget' },
      { t: '¿Cuál es la meta principal: leads, ventas o marca?' },
      { t: '¿Hay presupuesto de pauta? ¿Cuánto al mes?' },
      { t: 'Redes: ¿siguen siendo lo principal? Las reacciones lo bajaron.', ifLevel: ['social', 1] }
    ],
    boolean: {
      titles: '("coordinador de marketing" OR "coordinadora de marketing" OR "marketing digital" OR "especialista de marketing")',
      base: '(marketing)'
    },
    cards: [
      { letter: 'A', title: 'Community manager', company: 'restaurante',
        fields: [['Experiencia', '2 años'], ['Canales', 'Instagram, TikTok'], ['Pauta', 'No'], ['Mide', 'Seguidores'], ['Sector', 'Consumo'], ['Aspiración', '$800']],
        no: [{ t: 'Solo publica, no mide', fx: { analytics: 20, n_cm: 1 } }, { t: 'Muy junior', fx: { exp: 20 } }],
        yes: [{ t: 'Buen contenido', fx: { content: 20 } }] },
      { letter: 'B', title: 'Especialista de pauta digital', company: 'agencia',
        fields: [['Experiencia', '4 años'], ['Canales', 'Meta Ads, Google Ads'], ['Pauta', '$15k al mes'], ['Mide', 'GA4, costo por lead'], ['Sector', 'Varios clientes'], ['Aspiración', '$1,800']],
        yes: [{ t: 'Maneja pauta', fx: { paid: 35 } }, { t: 'Mide resultados', fx: { analytics: 35 } }, { t: 'Las redes no son lo principal', fx: { social: -25 } }],
        no: [{ t: 'Solo agencia, no marca', fx: {} }] },
      { letter: 'C', title: 'Coordinadora de marketing', company: 'empresa de software B2B',
        fields: [['Experiencia', '5 años'], ['Canales', 'LinkedIn, correo'], ['Pauta', 'LinkedIn Ads'], ['Mide', 'Leads calificados'], ['Extra', 'Eventos y webinars'], ['Aspiración', '$2,000']],
        yes: [{ t: 'Marketing B2B', fx: { b2b: 40 } }, { t: 'Organiza eventos', fx: { events: 30 } }, { t: 'Mide leads', fx: { analytics: 15 } }],
        no: [{ t: 'Poca pauta en Meta', fx: { paid: 15 } }] },
      { letter: 'D', title: 'Gerente de marketing', company: 'banco',
        fields: [['Experiencia', '10 años'], ['Equipo', '6 personas'], ['Pauta', 'Agencias externas'], ['Mide', 'Marca y ventas'], ['Sector', 'Banca'], ['Aspiración', '$4,000']],
        no: [{ t: 'Fuera de presupuesto', fx: { db_budget: 1 } }, { t: 'Sobrecalificado', fx: { exp: -5 } }],
        yes: [{ t: 'Visión de negocio', fx: { analytics: 10 } }] },
      { letter: 'E', title: 'Creadora de contenido', company: 'independiente',
        fields: [['Experiencia', '3 años'], ['Canales', 'TikTok, Reels'], ['Pauta', 'No'], ['Mide', 'Vistas'], ['Fuerte en', 'Video'], ['Aspiración', '$1,200']],
        no: [{ t: 'Solo contenido, sin estrategia', fx: { n_cm: 1, analytics: 15 } }, { t: 'Sin pauta', fx: { paid: 20 } }],
        yes: [{ t: 'Video de calidad', fx: { content: 25 } }] },
      { letter: 'F', title: 'Analista de marketing', company: 'cadena de retail',
        fields: [['Experiencia', '4 años'], ['Canales', 'Meta Ads, correo'], ['Pauta', 'Sí'], ['Mide', 'GA4, ventas'], ['Sector', 'Consumo'], ['Aspiración', '$1,700']],
        yes: [{ t: 'Domina analítica', fx: { analytics: 25 } }, { t: 'Maneja pauta', fx: { paid: 20 } }],
        no: [{ t: 'Sin experiencia B2B', fx: { b2b: 25 } }] }
    ]
  }
];
