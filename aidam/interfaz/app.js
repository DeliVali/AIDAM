/* AIDAM — lógica de la interfaz. Vanilla JS, sin dependencias.
 *
 * Protocolo WebSocket documentado en aidam/servidor.py y docs/INTERFAZ.md.
 * Layout tipo chat: barra lateral con espacios de trabajo y conversaciones
 * continuables; modo de ejecución como icono junto a la entrada; idioma y
 * memoria en el engranaje de configuración. Sin voz por diseño.
 *
 * i18n: el idioma elegido cambia TODA la interfaz y el idioma de las
 * afirmaciones que se verifican. Seis idiomas con diccionario completo
 * (es, en, fr, de, pt, it); añadir uno = añadir su diccionario a TEXTOS
 * (la comprobación de simetría vive en el flujo de verificación).
 */

"use strict";

// ------------------------------------------------------------------ i18n ----

const TEXTOS = {
  es: {
    nuevaVerificacion: "＋ Nueva verificación",
    espacios: "Espacios de trabajo",
    general: "General",
    generalTitulo: "Espacio general: siempre disponible, sin carpeta que elegir",
    ejemplos: ["La Torre Eiffel está en París", "El aluminio de las vacunas causa autismo", "La Gran Muralla China se ve desde el espacio"],
    anadirCarpeta: "Añadir carpeta…",
    anadirCarpetaTitulo: "Añadir una carpeta como espacio de trabajo",
    quitarEspacio: "Quitar este espacio de la lista (sus conversaciones no se borran)",
    rutaCarpeta: "Ruta de la carpeta a añadir como espacio de trabajo:",
    conversaciones: "Conversaciones",
    sinConversaciones: "Sin conversaciones todavía.",
    sinTitulo: "(Sin título)",
    turnos: (n) => `${n} turno${n === 1 ? "" : "s"}`,
    reabrir: "Reabrir y continuar esta conversación",
    conectando: "Conectando…",
    conectado: "Conectado",
    desconectado: "Desconectado",
    estadoTitulo: "Estado de la conexión",
    configTitulo: "Configuración",
    idioma: "Idioma",
    memoria: "Memoria",
    memoriaTitulo: "Guardar en la memoria del agente y avisar si ya se verificó antes",
    entradaPlaceholder: "Escribe una afirmación para verificar, o adjunta un documento…",
    adjuntarTitulo: "Subir un documento",
    menuAdjuntar: "¿Qué documento subes?",
    opcionImagen: "🖼 Imagen o captura",
    opcionPdf: "📄 PDF",
    opcionTexto: "📃 Texto (.txt, .md)",
    enviarTitulo: "Verificar (Enter)",
    detenerTitulo: "Detener la verificación",
    menuModo: "Modo de ejecución",
    modoAuto: "⚡ Automático",
    modoPermisos: "🔒 Pedir permiso",
    modoTitulo: (m) => `Modo: ${m} (clic para cambiar)`,
    bienvenidaTitulo: "¿Qué verificamos hoy?",
    bienvenidaTexto: "AIDAM descompone la afirmación, busca evidencia en fuentes " +
      "independientes, la juzga con un modelo especializado y responde con sus citas.",
    sustentado: "Sustentado",
    refutado: "Refutado",
    contradictorio: "Evidencia contradictoria",
    insuficiente: "Evidencia insuficiente",
    respuesta: "Respuesta",
    tarea: "Tarea completada",
    modoTarea: "Modo tarea",
    modoTareaTitulo: "El razonador local ejecuta tareas con herramientas y permisos (experimental)",
    confianza: (n) => `CONFIANZA ${n}%`,
    citas: (n) => `${n} cita${n === 1 ? "" : "s"}`,
    aFavor: (n) => `${n} a favor`,
    enContra: (n) => `${n} en contra`,
    sinEvidencia: "Sin evidencia concluyente en las fuentes consultadas.",
    verProceso: (n) => `Ver el proceso (${n} pasos)`,
    permisoTitulo: "🔒 El agente pide permiso",
    permitir: "Permitir",
    permitirTodo: "Permitir todo",
    permitirTodoTitulo: "Aprueba esta acción y el resto de la verificación sigue en automático",
    denegar: "Denegar",
    resPermitido: "✓ Permitido",
    resPermitidoTodo: "✓ Permitido todo — el resto sigue en automático",
    resDenegado: "✗ Denegado — esa búsqueda se omite",
    cancelada: "Verificación cancelada.",
    chipMemoria: (fecha, veredicto, conf) =>
      `🕊 Ya verificada el ${fecha}: ${veredicto} (confianza ${conf}%) — se vuelve a verificar igualmente`,
    esperaEnCurso: "Espera a que termine la verificación en curso (o cancélala).",
    noAbrir: (e) => `No se pudo abrir la conversación: ${e}`,
    extrayendo: (n) => `Extrayendo texto de ${n}…`,
    extraido: (n, r) => `Texto extraído de ${n}${r} — revísalo antes de verificar`,
    recortado: (n) => ` (recortado a ${n} caracteres)`,
    sinTextoLegible: (n) => `${n} no contiene texto legible`,
    noLeer: (n, e) => `No se pudo leer ${n}: ${e}`,
    ocrFalta: "OCR de imágenes no instalado en el servidor: «uv pip install -e '.[imagen]'» y reinicia AIDAM.",
    pdfFalta: "Lectura de PDF no instalada: «uv pip install -e '.[interfaz]'» y reinicia AIDAM.",
  },
  en: {
    nuevaVerificacion: "＋ New verification",
    espacios: "Workspaces",
    general: "General",
    generalTitulo: "General workspace: always available, no folder needed",
    ejemplos: ["The Eiffel Tower is in Paris", "Vaccine aluminum causes autism", "The Great Wall of China is visible from space"],
    anadirCarpeta: "Add folder…",
    anadirCarpetaTitulo: "Add a folder as a workspace",
    quitarEspacio: "Remove this workspace from the list (its conversations are kept)",
    rutaCarpeta: "Path of the folder to add as a workspace:",
    conversaciones: "Conversations",
    sinConversaciones: "No conversations yet.",
    sinTitulo: "(Untitled)",
    turnos: (n) => `${n} turn${n === 1 ? "" : "s"}`,
    reabrir: "Reopen and continue this conversation",
    conectando: "Connecting…",
    conectado: "Connected",
    desconectado: "Disconnected",
    estadoTitulo: "Connection status",
    configTitulo: "Settings",
    idioma: "Language",
    memoria: "Memory",
    memoriaTitulo: "Save to the agent's memory and warn if it was verified before",
    entradaPlaceholder: "Write a claim to verify, or attach a document…",
    adjuntarTitulo: "Upload a document",
    menuAdjuntar: "What are you uploading?",
    opcionImagen: "🖼 Image or screenshot",
    opcionPdf: "📄 PDF",
    opcionTexto: "📃 Text (.txt, .md)",
    enviarTitulo: "Verify (Enter)",
    detenerTitulo: "Stop the verification",
    menuModo: "Execution mode",
    modoAuto: "⚡ Automatic",
    modoPermisos: "🔒 Ask permission",
    modoTitulo: (m) => `Mode: ${m} (click to change)`,
    bienvenidaTitulo: "What shall we verify today?",
    bienvenidaTexto: "AIDAM breaks the claim into facts, retrieves evidence from " +
      "independent sources, judges it with a specialized model and answers with its citations.",
    sustentado: "Supported",
    refutado: "Refuted",
    contradictorio: "Conflicting evidence",
    insuficiente: "Not enough evidence",
    respuesta: "Answer",
    tarea: "Task completed",
    modoTarea: "Task mode",
    modoTareaTitulo: "The local reasoner runs tasks with tools and permissions (experimental)",
    confianza: (n) => `CONFIDENCE ${n}%`,
    citas: (n) => `${n} citation${n === 1 ? "" : "s"}`,
    aFavor: (n) => `${n} for`,
    enContra: (n) => `${n} against`,
    sinEvidencia: "No conclusive evidence in the consulted sources.",
    verProceso: (n) => `See the process (${n} steps)`,
    permisoTitulo: "🔒 The agent asks for permission",
    permitir: "Allow",
    permitirTodo: "Allow all",
    permitirTodoTitulo: "Approve this action; the rest of the run continues automatically",
    denegar: "Deny",
    resPermitido: "✓ Allowed",
    resPermitidoTodo: "✓ All allowed — the rest continues automatically",
    resDenegado: "✗ Denied — that search is skipped",
    cancelada: "Verification cancelled.",
    chipMemoria: (fecha, veredicto, conf) =>
      `🕊 Already verified on ${fecha}: ${veredicto} (confidence ${conf}%) — it is re-verified anyway`,
    esperaEnCurso: "Wait for the current verification to finish (or cancel it).",
    noAbrir: (e) => `Could not open the conversation: ${e}`,
    extrayendo: (n) => `Extracting text from ${n}…`,
    extraido: (n, r) => `Text extracted from ${n}${r} — review it before verifying`,
    recortado: (n) => ` (trimmed to ${n} characters)`,
    sinTextoLegible: (n) => `${n} contains no readable text`,
    noLeer: (n, e) => `Could not read ${n}: ${e}`,
    ocrFalta: "Image OCR is not installed on the server: «uv pip install -e '.[imagen]'» and restart AIDAM.",
    pdfFalta: "PDF reading is not installed: «uv pip install -e '.[interfaz]'» and restart AIDAM.",
  },
  fr: {
    nuevaVerificacion: "＋ Nouvelle vérification",
    espacios: "Espaces de travail",
    general: "Général",
    ejemplos: ["La tour Eiffel est à Paris", "L'aluminium des vaccins cause l'autisme", "La Grande Muraille de Chine est visible depuis l'espace"],
    generalTitulo: "Espace général : toujours disponible, aucun dossier à choisir",
    anadirCarpeta: "Ajouter un dossier…",
    anadirCarpetaTitulo: "Ajouter un dossier comme espace de travail",
    quitarEspacio: "Retirer cet espace de la liste (ses conversations sont conservées)",
    rutaCarpeta: "Chemin du dossier à ajouter comme espace de travail :",
    conversaciones: "Conversations",
    sinConversaciones: "Aucune conversation pour l'instant.",
    sinTitulo: "(Sans titre)",
    turnos: (n) => `${n} tour${n === 1 ? "" : "s"}`,
    reabrir: "Rouvrir et poursuivre cette conversation",
    conectando: "Connexion…",
    conectado: "Connecté",
    desconectado: "Déconnecté",
    estadoTitulo: "État de la connexion",
    configTitulo: "Paramètres",
    idioma: "Langue",
    memoria: "Mémoire",
    memoriaTitulo: "Enregistrer dans la mémoire de l'agent et prévenir si déjà vérifiée",
    entradaPlaceholder: "Écrivez une affirmation à vérifier, ou joignez un document…",
    adjuntarTitulo: "Joindre un document",
    menuAdjuntar: "Quel document envoyez-vous ?",
    opcionImagen: "🖼 Image ou capture",
    opcionPdf: "📄 PDF",
    opcionTexto: "📃 Texte (.txt, .md)",
    enviarTitulo: "Vérifier (Entrée)",
    detenerTitulo: "Arrêter la vérification",
    menuModo: "Mode d'exécution",
    modoAuto: "⚡ Automatique",
    modoPermisos: "🔒 Demander la permission",
    modoTitulo: (m) => `Mode : ${m} (cliquez pour changer)`,
    bienvenidaTitulo: "Que vérifions-nous aujourd'hui ?",
    bienvenidaTexto: "AIDAM décompose l'affirmation, cherche des preuves dans des " +
      "sources indépendantes, les juge avec un modèle spécialisé et répond avec ses citations.",
    sustentado: "Confirmée",
    refutado: "Réfutée",
    contradictorio: "Preuves contradictoires",
    insuficiente: "Preuves insuffisantes",
    respuesta: "Réponse",
    tarea: "Tâche terminée",
    modoTarea: "Mode tâche",
    modoTareaTitulo: "Le raisonneur local exécute des tâches avec outils et permissions (expérimental)",
    confianza: (n) => `CONFIANCE ${n}%`,
    citas: (n) => `${n} citation${n === 1 ? "" : "s"}`,
    aFavor: (n) => `${n} pour`,
    enContra: (n) => `${n} contre`,
    sinEvidencia: "Aucune preuve concluante dans les sources consultées.",
    verProceso: (n) => `Voir le processus (${n} étapes)`,
    permisoTitulo: "🔒 L'agent demande la permission",
    permitir: "Autoriser",
    permitirTodo: "Tout autoriser",
    permitirTodoTitulo: "Approuve cette action ; le reste continue automatiquement",
    denegar: "Refuser",
    resPermitido: "✓ Autorisé",
    resPermitidoTodo: "✓ Tout autorisé — le reste continue automatiquement",
    resDenegado: "✗ Refusé — cette recherche est ignorée",
    cancelada: "Vérification annulée.",
    chipMemoria: (fecha, veredicto, conf) =>
      `🕊 Déjà vérifiée le ${fecha} : ${veredicto} (confiance ${conf}%) — elle est revérifiée quand même`,
    esperaEnCurso: "Attendez la fin de la vérification en cours (ou annulez-la).",
    noAbrir: (e) => `Impossible d'ouvrir la conversation : ${e}`,
    extrayendo: (n) => `Extraction du texte de ${n}…`,
    extraido: (n, r) => `Texte extrait de ${n}${r} — relisez-le avant de vérifier`,
    recortado: (n) => ` (tronqué à ${n} caractères)`,
    sinTextoLegible: (n) => `${n} ne contient pas de texte lisible`,
    noLeer: (n, e) => `Impossible de lire ${n} : ${e}`,
    ocrFalta: "OCR d'images non installé sur le serveur : «uv pip install -e '.[imagen]'» puis redémarrez AIDAM.",
    pdfFalta: "Lecture PDF non installée : «uv pip install -e '.[interfaz]'» puis redémarrez AIDAM.",
  },
  de: {
    nuevaVerificacion: "＋ Neue Überprüfung",
    espacios: "Arbeitsbereiche",
    general: "Allgemein",
    ejemplos: ["Der Eiffelturm steht in Paris", "Aluminium in Impfstoffen verursacht Autismus", "Die Chinesische Mauer ist aus dem All sichtbar"],
    generalTitulo: "Allgemeiner Bereich: immer verfügbar, kein Ordner nötig",
    anadirCarpeta: "Ordner hinzufügen…",
    anadirCarpetaTitulo: "Einen Ordner als Arbeitsbereich hinzufügen",
    quitarEspacio: "Diesen Bereich aus der Liste entfernen (seine Unterhaltungen bleiben erhalten)",
    rutaCarpeta: "Pfad des Ordners, der als Arbeitsbereich hinzugefügt wird:",
    conversaciones: "Unterhaltungen",
    sinConversaciones: "Noch keine Unterhaltungen.",
    sinTitulo: "(Ohne Titel)",
    turnos: (n) => `${n} ${n === 1 ? "Runde" : "Runden"}`,
    reabrir: "Diese Unterhaltung erneut öffnen und fortsetzen",
    conectando: "Verbinde…",
    conectado: "Verbunden",
    desconectado: "Getrennt",
    estadoTitulo: "Verbindungsstatus",
    configTitulo: "Einstellungen",
    idioma: "Sprache",
    memoria: "Gedächtnis",
    memoriaTitulo: "Im Gedächtnis des Agenten speichern und warnen, wenn bereits überprüft",
    entradaPlaceholder: "Schreibe eine Behauptung zur Überprüfung oder hänge ein Dokument an…",
    adjuntarTitulo: "Dokument hochladen",
    menuAdjuntar: "Was lädst du hoch?",
    opcionImagen: "🖼 Bild oder Screenshot",
    opcionPdf: "📄 PDF",
    opcionTexto: "📃 Text (.txt, .md)",
    enviarTitulo: "Überprüfen (Enter)",
    detenerTitulo: "Überprüfung stoppen",
    menuModo: "Ausführungsmodus",
    modoAuto: "⚡ Automatisch",
    modoPermisos: "🔒 Erlaubnis erfragen",
    modoTitulo: (m) => `Modus: ${m} (zum Wechseln klicken)`,
    bienvenidaTitulo: "Was überprüfen wir heute?",
    bienvenidaTexto: "AIDAM zerlegt die Behauptung, sucht Belege in unabhängigen " +
      "Quellen, beurteilt sie mit einem spezialisierten Modell und antwortet mit Quellenangaben.",
    sustentado: "Belegt",
    refutado: "Widerlegt",
    contradictorio: "Widersprüchliche Belege",
    insuficiente: "Unzureichende Belege",
    respuesta: "Antwort",
    tarea: "Aufgabe abgeschlossen",
    modoTarea: "Aufgabenmodus",
    modoTareaTitulo: "Der lokale Reasoner führt Aufgaben mit Werkzeugen und Berechtigungen aus (experimentell)",
    confianza: (n) => `KONFIDENZ ${n}%`,
    citas: (n) => `${n} Zitat${n === 1 ? "" : "e"}`,
    aFavor: (n) => `${n} dafür`,
    enContra: (n) => `${n} dagegen`,
    sinEvidencia: "Keine schlüssigen Belege in den befragten Quellen.",
    verProceso: (n) => `Prozess ansehen (${n} Schritte)`,
    permisoTitulo: "🔒 Der Agent bittet um Erlaubnis",
    permitir: "Erlauben",
    permitirTodo: "Alles erlauben",
    permitirTodoTitulo: "Genehmigt diese Aktion; der Rest läuft automatisch weiter",
    denegar: "Ablehnen",
    resPermitido: "✓ Erlaubt",
    resPermitidoTodo: "✓ Alles erlaubt — der Rest läuft automatisch",
    resDenegado: "✗ Abgelehnt — diese Suche wird übersprungen",
    cancelada: "Überprüfung abgebrochen.",
    chipMemoria: (fecha, veredicto, conf) =>
      `🕊 Bereits am ${fecha} überprüft: ${veredicto} (Konfidenz ${conf}%) — wird trotzdem erneut überprüft`,
    esperaEnCurso: "Warte, bis die laufende Überprüfung endet (oder brich sie ab).",
    noAbrir: (e) => `Unterhaltung konnte nicht geöffnet werden: ${e}`,
    extrayendo: (n) => `Text wird aus ${n} extrahiert…`,
    extraido: (n, r) => `Text aus ${n} extrahiert${r} — prüfe ihn vor der Überprüfung`,
    recortado: (n) => ` (auf ${n} Zeichen gekürzt)`,
    sinTextoLegible: (n) => `${n} enthält keinen lesbaren Text`,
    noLeer: (n, e) => `${n} konnte nicht gelesen werden: ${e}`,
    ocrFalta: "Bild-OCR ist auf dem Server nicht installiert: «uv pip install -e '.[imagen]'» und AIDAM neu starten.",
    pdfFalta: "PDF-Unterstützung ist nicht installiert: «uv pip install -e '.[interfaz]'» und AIDAM neu starten.",
  },
  pt: {
    nuevaVerificacion: "＋ Nova verificação",
    espacios: "Espaços de trabalho",
    general: "Geral",
    ejemplos: ["A Torre Eiffel fica em Paris", "O alumínio das vacinas causa autismo", "A Grande Muralha da China é visível do espaço"],
    generalTitulo: "Espaço geral: sempre disponível, sem pasta para escolher",
    anadirCarpeta: "Adicionar pasta…",
    anadirCarpetaTitulo: "Adicionar uma pasta como espaço de trabalho",
    quitarEspacio: "Remover este espaço da lista (as conversas são mantidas)",
    rutaCarpeta: "Caminho da pasta a adicionar como espaço de trabalho:",
    conversaciones: "Conversas",
    sinConversaciones: "Ainda sem conversas.",
    sinTitulo: "(Sem título)",
    turnos: (n) => `${n} turno${n === 1 ? "" : "s"}`,
    reabrir: "Reabrir e continuar esta conversa",
    conectando: "Conectando…",
    conectado: "Conectado",
    desconectado: "Desconectado",
    estadoTitulo: "Estado da conexão",
    configTitulo: "Configurações",
    idioma: "Idioma",
    memoria: "Memória",
    memoriaTitulo: "Guardar na memória do agente e avisar se já foi verificada",
    entradaPlaceholder: "Escreva uma afirmação para verificar, ou anexe um documento…",
    adjuntarTitulo: "Enviar um documento",
    menuAdjuntar: "Qual documento você envia?",
    opcionImagen: "🖼 Imagem ou captura",
    opcionPdf: "📄 PDF",
    opcionTexto: "📃 Texto (.txt, .md)",
    enviarTitulo: "Verificar (Enter)",
    detenerTitulo: "Parar a verificação",
    menuModo: "Modo de execução",
    modoAuto: "⚡ Automático",
    modoPermisos: "🔒 Pedir permissão",
    modoTitulo: (m) => `Modo: ${m} (clique para mudar)`,
    bienvenidaTitulo: "O que verificamos hoje?",
    bienvenidaTexto: "O AIDAM decompõe a afirmação, busca evidências em fontes " +
      "independentes, julga-as com um modelo especializado e responde com suas citações.",
    sustentado: "Sustentada",
    refutado: "Refutada",
    contradictorio: "Evidências contraditórias",
    insuficiente: "Evidências insuficientes",
    respuesta: "Resposta",
    tarea: "Tarefa concluída",
    modoTarea: "Modo tarefa",
    modoTareaTitulo: "O raciocinador local executa tarefas com ferramentas e permissões (experimental)",
    confianza: (n) => `CONFIANÇA ${n}%`,
    citas: (n) => `${n} citaç${n === 1 ? "ão" : "ões"}`,
    aFavor: (n) => `${n} a favor`,
    enContra: (n) => `${n} contra`,
    sinEvidencia: "Sem evidência conclusiva nas fontes consultadas.",
    verProceso: (n) => `Ver o processo (${n} passos)`,
    permisoTitulo: "🔒 O agente pede permissão",
    permitir: "Permitir",
    permitirTodo: "Permitir tudo",
    permitirTodoTitulo: "Aprova esta ação; o resto continua automaticamente",
    denegar: "Negar",
    resPermitido: "✓ Permitido",
    resPermitidoTodo: "✓ Tudo permitido — o resto continua automático",
    resDenegado: "✗ Negado — essa busca é ignorada",
    cancelada: "Verificação cancelada.",
    chipMemoria: (fecha, veredicto, conf) =>
      `🕊 Já verificada em ${fecha}: ${veredicto} (confiança ${conf}%) — é verificada novamente mesmo assim`,
    esperaEnCurso: "Espere a verificação em curso terminar (ou cancele-a).",
    noAbrir: (e) => `Não foi possível abrir a conversa: ${e}`,
    extrayendo: (n) => `Extraindo texto de ${n}…`,
    extraido: (n, r) => `Texto extraído de ${n}${r} — revise antes de verificar`,
    recortado: (n) => ` (cortado em ${n} caracteres)`,
    sinTextoLegible: (n) => `${n} não contém texto legível`,
    noLeer: (n, e) => `Não foi possível ler ${n}: ${e}`,
    ocrFalta: "OCR de imagens não instalado no servidor: «uv pip install -e '.[imagen]'» e reinicie o AIDAM.",
    pdfFalta: "Leitura de PDF não instalada: «uv pip install -e '.[interfaz]'» e reinicie o AIDAM.",
  },
  it: {
    nuevaVerificacion: "＋ Nuova verifica",
    espacios: "Spazi di lavoro",
    general: "Generale",
    ejemplos: ["La Torre Eiffel è a Parigi", "L'alluminio nei vaccini causa l'autismo", "La Grande Muraglia cinese è visibile dallo spazio"],
    generalTitulo: "Spazio generale: sempre disponibile, nessuna cartella da scegliere",
    anadirCarpeta: "Aggiungi cartella…",
    anadirCarpetaTitulo: "Aggiungi una cartella come spazio di lavoro",
    quitarEspacio: "Rimuovi questo spazio dall'elenco (le conversazioni restano)",
    rutaCarpeta: "Percorso della cartella da aggiungere come spazio di lavoro:",
    conversaciones: "Conversazioni",
    sinConversaciones: "Ancora nessuna conversazione.",
    sinTitulo: "(Senza titolo)",
    turnos: (n) => `${n} turn${n === 1 ? "o" : "i"}`,
    reabrir: "Riapri e continua questa conversazione",
    conectando: "Connessione…",
    conectado: "Connesso",
    desconectado: "Disconnesso",
    estadoTitulo: "Stato della connessione",
    configTitulo: "Impostazioni",
    idioma: "Lingua",
    memoria: "Memoria",
    memoriaTitulo: "Salva nella memoria dell'agente e avvisa se già verificata",
    entradaPlaceholder: "Scrivi un'affermazione da verificare, o allega un documento…",
    adjuntarTitulo: "Carica un documento",
    menuAdjuntar: "Che documento carichi?",
    opcionImagen: "🖼 Immagine o screenshot",
    opcionPdf: "📄 PDF",
    opcionTexto: "📃 Testo (.txt, .md)",
    enviarTitulo: "Verifica (Invio)",
    detenerTitulo: "Ferma la verifica",
    menuModo: "Modalità di esecuzione",
    modoAuto: "⚡ Automatica",
    modoPermisos: "🔒 Chiedi permesso",
    modoTitulo: (m) => `Modalità: ${m} (clic per cambiare)`,
    bienvenidaTitulo: "Cosa verifichiamo oggi?",
    bienvenidaTexto: "AIDAM scompone l'affermazione, cerca prove in fonti " +
      "indipendenti, le giudica con un modello specializzato e risponde con le sue citazioni.",
    sustentado: "Confermata",
    refutado: "Confutata",
    contradictorio: "Prove contrastanti",
    insuficiente: "Prove insufficienti",
    respuesta: "Risposta",
    tarea: "Attività completata",
    modoTarea: "Modalità attività",
    modoTareaTitulo: "Il ragionatore locale esegue attività con strumenti e permessi (sperimentale)",
    confianza: (n) => `FIDUCIA ${n}%`,
    citas: (n) => `${n} citazion${n === 1 ? "e" : "i"}`,
    aFavor: (n) => `${n} a favore`,
    enContra: (n) => `${n} contro`,
    sinEvidencia: "Nessuna prova conclusiva nelle fonti consultate.",
    verProceso: (n) => `Vedi il processo (${n} passi)`,
    permisoTitulo: "🔒 L'agente chiede il permesso",
    permitir: "Consenti",
    permitirTodo: "Consenti tutto",
    permitirTodoTitulo: "Approva questa azione; il resto continua in automatico",
    denegar: "Nega",
    resPermitido: "✓ Consentito",
    resPermitidoTodo: "✓ Tutto consentito — il resto continua in automatico",
    resDenegado: "✗ Negato — quella ricerca viene saltata",
    cancelada: "Verifica annullata.",
    chipMemoria: (fecha, veredicto, conf) =>
      `🕊 Già verificata il ${fecha}: ${veredicto} (fiducia ${conf}%) — viene comunque riverificata`,
    esperaEnCurso: "Aspetta che finisca la verifica in corso (o annullala).",
    noAbrir: (e) => `Impossibile aprire la conversazione: ${e}`,
    extrayendo: (n) => `Estrazione del testo da ${n}…`,
    extraido: (n, r) => `Testo estratto da ${n}${r} — rileggilo prima di verificare`,
    recortado: (n) => ` (tagliato a ${n} caratteri)`,
    sinTextoLegible: (n) => `${n} non contiene testo leggibile`,
    noLeer: (n, e) => `Impossibile leggere ${n}: ${e}`,
    ocrFalta: "OCR delle immagini non installato sul server: «uv pip install -e '.[imagen]'» e riavvia AIDAM.",
    pdfFalta: "Lettura PDF non installata: «uv pip install -e '.[interfaz]'» e riavvia AIDAM.",
  },
};

function idiomaInterfaz() {
  const elegido = ui.idioma?.value || "es";
  return TEXTOS[elegido] ? elegido : "en"; // fr/de/pt/it: interfaz en inglés
}

function t(clave, ...args) {
  const texto = TEXTOS[idiomaInterfaz()][clave] ?? TEXTOS.es[clave] ?? clave;
  return typeof texto === "function" ? texto(...args) : texto;
}

// ---------------------------------------------------------------- estado ----

const $ = (id) => document.getElementById(id);

const ui = {
  conversacion: $("conversacion"),
  plantillaBienvenida: $("plantilla-bienvenida"),
  entrada: $("entrada"),
  enviar: $("boton-enviar"),
  adjuntar: $("boton-adjuntar"),
  menuAdjuntar: $("menu-adjuntar"),
  selectorArchivo: $("selector-archivo"),
  avisoAdjunto: $("aviso-adjunto"),
  botonModo: $("boton-modo"),
  menuModo: $("menu-modo"),
  idioma: $("idioma"),
  memoria: $("opcion-memoria"),
  tareas: $("opcion-tareas"),
  botonConfig: $("boton-config"),
  menuConfig: $("menu-config"),
  estadoConexion: $("estado-conexion"),
  estadoTexto: $("estado-texto"),
  avisos: $("avisos"),
  nuevaVerificacion: $("nueva-verificacion"),
  listaEspacios: $("lista-espacios"),
  anadirCarpeta: $("boton-anadir-carpeta"),
  listaConversaciones: $("lista-conversaciones"),
  acercaVersion: $("acerca-version"),
};

const estado = {
  ws: null,
  conectado: false,
  intentoReconexion: 0,
  enCurso: false,      // hay una verificación corriendo
  turno: null,         // elementos DOM del turno activo
  capacidades: { imagen: false, pdf: false },
  tipoAdjunto: null,   // "imagen" | "pdf" | "texto" elegido en el menú
  modo: "auto",        // "auto" | "permisos"
  carpetas: [],        // espacios añadidos por el usuario (rutas absolutas)
  espacio: null,       // espacio activo: null = General, o una ruta de carpetas
  conversacion: null,  // id de la conversación activa (null = aún sin crear)
};

function infoVeredicto(veredicto) {
  const mapa = {
    sustentado: { clase: "sustentado", icono: "✓", clave: "sustentado" },
    refutado: { clase: "refutado", icono: "✗", clave: "refutado" },
    evidencia_contradictoria: { clase: "contradictorio", icono: "⚡", clave: "contradictorio" },
    evidencia_insuficiente: { clase: "insuficiente", icono: "?", clave: "insuficiente" },
  };
  const info = mapa[veredicto] || mapa.evidencia_insuficiente;
  return { ...info, titulo: t(info.clave) };
}

const MAX_TEXTO_DOCUMENTO = 4000; // lo que se vuelca al cuadro de entrada

// ------------------------------------------------------------ utilidades ----

function crear(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function avisar(mensaje, esError) {
  const aviso = crear("div", "aviso" + (esError ? " error" : ""), mensaje);
  ui.avisos.appendChild(aviso);
  setTimeout(() => aviso.remove(), 7000);
}

function bajarConversacion() {
  ui.conversacion.scrollTop = ui.conversacion.scrollHeight;
}

function fechaCorta(iso) {
  try {
    return new Date(iso).toLocaleString(ui.idioma?.value || undefined, {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function tituloVeredicto(v) {
  const titulo = crear("div", "veredicto-titulo");
  titulo.appendChild(crear("span", "punto-veredicto"));
  titulo.appendChild(crear("span", null, v.titulo.toUpperCase()));
  return titulo;
}

// ------------------------------------------------- idioma: aplicar a la UI ----

function aplicarIdioma() {
  document.documentElement.lang = ui.idioma.value;

  ui.nuevaVerificacion.textContent = t("nuevaVerificacion");
  $("etiqueta-espacios").textContent = t("espacios");
  $("etiqueta-conversaciones").textContent = t("conversaciones");
  ui.anadirCarpeta.title = t("anadirCarpetaTitulo");
  ui.anadirCarpeta.querySelector(".carpeta-nombre").textContent = t("anadirCarpeta");

  ui.entrada.placeholder = t("entradaPlaceholder");
  ui.adjuntar.title = t("adjuntarTitulo");
  $("menu-adjuntar-titulo").textContent = t("menuAdjuntar");
  const opciones = ui.menuAdjuntar.querySelectorAll(".menu-opcion");
  opciones[0].textContent = t("opcionImagen");
  opciones[1].textContent = t("opcionPdf");
  opciones[2].textContent = t("opcionTexto");

  $("menu-modo-titulo").textContent = t("menuModo");
  ui.menuModo.querySelector('[data-modo="auto"]').textContent = t("modoAuto");
  ui.menuModo.querySelector('[data-modo="permisos"]').textContent = t("modoPermisos");
  actualizarBotonModo();

  if (!estado.enCurso) ui.enviar.title = t("enviarTitulo");
  ui.estadoConexion.title = t("estadoTitulo");
  ui.estadoTexto.textContent = estado.conectado
    ? t("conectado")
    : (estado.intentoReconexion ? t("desconectado") : t("conectando"));

  ui.botonConfig.title = t("configTitulo");
  $("menu-config-titulo").textContent = t("configTitulo");
  $("etiqueta-idioma").textContent = t("idioma");
  $("etiqueta-memoria").textContent = t("memoria");
  $("control-memoria").title = t("memoriaTitulo");
  $("etiqueta-tareas").textContent = t("modoTarea");
  $("control-tareas").title = t("modoTareaTitulo");

  // La plantilla de bienvenida se traduce en origen: los clones futuros y el
  // ejemplar visible (si lo hay) quedan en el idioma elegido.
  const plantilla = ui.plantillaBienvenida.content;
  plantilla.querySelector("h1").textContent = t("bienvenidaTitulo");
  plantilla.querySelector("p").textContent = t("bienvenidaTexto");
  const ejemplos = t("ejemplos");
  const traducirEjemplos = (raiz) => {
    raiz.querySelectorAll(".ejemplo").forEach((boton, i) => {
      if (ejemplos[i]) boton.textContent = ejemplos[i];
    });
  };
  traducirEjemplos(plantilla);
  const visible = ui.conversacion.querySelector(".bienvenida");
  if (visible) {
    visible.querySelector("h1").textContent = t("bienvenidaTitulo");
    visible.querySelector("p").textContent = t("bienvenidaTexto");
    traducirEjemplos(visible);
  }

  // El marcador estático de lista vacía también habla el idioma elegido
  // (cargarConversaciones lo reemplaza en cuanto el servidor responde).
  const vacio = ui.listaConversaciones.querySelector(".historial-vacio");
  if (vacio) vacio.textContent = t("sinConversaciones");

  renderEspacios();
  cargarConversaciones();
}

// ---------------------------------------------------------- preferencias ----

function cargarPreferencias() {
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem("aidam.prefs") || "{}"); } catch {}
  if (prefs.modo === "permisos") estado.modo = "permisos";
  if (TEXTOS[prefs.idioma]) ui.idioma.value = prefs.idioma;
  ui.memoria.checked = prefs.memoria !== false;
  estado.carpetas = Array.isArray(prefs.carpetas) ? prefs.carpetas : [];
  if (prefs.carpeta && !estado.carpetas.includes(prefs.carpeta)) {
    estado.carpetas.push(prefs.carpeta); // migración: carpeta única → lista
  }
  estado.espacio = estado.carpetas.includes(prefs.espacio) ? prefs.espacio : null;
}

function guardarPreferencias() {
  localStorage.setItem("aidam.prefs", JSON.stringify({
    modo: estado.modo,
    idioma: ui.idioma.value,
    memoria: ui.memoria.checked,
    carpetas: estado.carpetas,
    espacio: estado.espacio,
  }));
}

ui.idioma.addEventListener("change", () => { guardarPreferencias(); aplicarIdioma(); });
ui.memoria.addEventListener("change", guardarPreferencias);

// ------------------------------------------------------ modo de ejecución ----

function actualizarBotonModo() {
  const etiqueta = estado.modo === "permisos" ? t("modoPermisos") : t("modoAuto");
  ui.botonModo.textContent = etiqueta.slice(0, 2).trim(); // solo el emoji
  ui.botonModo.title = t("modoTitulo", etiqueta);
  ui.menuModo.querySelectorAll(".menu-opcion").forEach((boton) => {
    boton.classList.toggle("elegida", boton.dataset.modo === estado.modo);
  });
}

ui.botonModo.addEventListener("click", (e) => {
  e.stopPropagation();
  ui.menuModo.classList.toggle("oculto");
});

ui.menuModo.querySelectorAll(".menu-opcion").forEach((boton) => {
  boton.addEventListener("click", () => {
    estado.modo = boton.dataset.modo;
    guardarPreferencias();
    actualizarBotonModo();
    ui.menuModo.classList.add("oculto");
  });
});

// ----------------------------------------------------------- configuración ----

ui.botonConfig.addEventListener("click", (e) => {
  e.stopPropagation();
  ui.menuConfig.classList.toggle("oculto");
});

document.addEventListener("click", (e) => {
  for (const menu of [ui.menuAdjuntar, ui.menuModo, ui.menuConfig]) {
    if (!menu.classList.contains("oculto") && !menu.contains(e.target)) {
      menu.classList.add("oculto");
    }
  }
});

// -------------------------------------------------------------- websocket ----

function conectar() {
  const protocolo = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocolo}://${location.host}/ws`);
  estado.ws = ws;

  ws.onopen = () => {
    estado.conectado = true;
    estado.intentoReconexion = 0;
    ui.estadoConexion.className = "estado-conexion conectado";
    ui.estadoTexto.textContent = t("conectado");
    // Los fetch de arranque pueden perder la carrera contra un servidor que
    // aún despierta; el WS sí reintenta, así que al conectar se recargan.
    cargarConversaciones();
    if (ui.acercaVersion.textContent === "—") cargarCapacidades();
  };

  ws.onmessage = (evento) => {
    let mensaje;
    try { mensaje = JSON.parse(evento.data); } catch { return; }
    manejarMensaje(mensaje);
  };

  ws.onclose = () => {
    estado.conectado = false;
    ui.estadoConexion.className = "estado-conexion desconectado";
    ui.estadoTexto.textContent = t("desconectado");
    if (estado.enCurso) terminarTurno();
    const espera = Math.min(10000, 500 * 2 ** estado.intentoReconexion++);
    setTimeout(conectar, espera);
  };
}

function manejarMensaje(m) {
  switch (m.tipo) {
    case "progreso": return anotarProgreso(m.mensaje);
    case "conversacion": return engancharConversacion(m.id);
    case "permiso": return pedirPermiso(m);
    case "memoria": return mostrarMemoria(m.previas);
    case "informe": return mostrarInforme(m.informe);
    case "cancelado": return mostrarCancelado();
    case "error": return mostrarError(m.mensaje);
  }
}

function engancharConversacion(id) {
  // El servidor creó el hilo para este turno: los siguientes siguen en él.
  estado.conversacion = id;
}

// ------------------------------------------------------ espacios de trabajo ----

function nombreDeCarpeta(ruta) {
  return ruta.replace(/[/\\]+$/, "").split(/[/\\]/).pop() || ruta;
}

function renderEspacios() {
  ui.listaEspacios.replaceChildren();

  const general = crear("li");
  general.appendChild(crear("span", null, "🏠"));
  general.appendChild(crear("span", "espacio-nombre", t("general")));
  general.title = t("generalTitulo");
  general.classList.toggle("activa", estado.espacio === null);
  general.onclick = () => seleccionarEspacio(null);
  ui.listaEspacios.appendChild(general);

  for (const ruta of estado.carpetas) {
    const item = crear("li");
    item.appendChild(crear("span", null, "📁"));
    item.appendChild(crear("span", "espacio-nombre", nombreDeCarpeta(ruta)));
    item.title = ruta;
    item.classList.toggle("activa", estado.espacio === ruta);
    item.onclick = () => seleccionarEspacio(ruta);
    const quitar = crear("span", "espacio-quitar", "✕");
    quitar.title = t("quitarEspacio");
    quitar.onclick = (e) => {
      e.stopPropagation();
      estado.carpetas = estado.carpetas.filter((c) => c !== ruta);
      if (estado.espacio === ruta) seleccionarEspacio(null);
      else { guardarPreferencias(); renderEspacios(); }
    };
    item.appendChild(quitar);
    ui.listaEspacios.appendChild(item);
  }
}

function seleccionarEspacio(ruta) {
  estado.espacio = ruta;
  guardarPreferencias();
  renderEspacios();
  cargarConversaciones();
  nuevaConversacion();
}

async function anadirCarpeta() {
  let ruta = null;
  if (window.aidamEscritorio?.elegirCarpeta) {
    ruta = await window.aidamEscritorio.elegirCarpeta(); // diálogo nativo (app de escritorio)
  } else {
    // En navegador no hay diálogo con ruta real: entrada manual honesta.
    ruta = prompt(t("rutaCarpeta"), "~/");
  }
  if (!ruta) return;
  ruta = ruta.trim();
  if (!estado.carpetas.includes(ruta)) estado.carpetas.push(ruta);
  seleccionarEspacio(ruta);
}

ui.anadirCarpeta.addEventListener("click", anadirCarpeta);

// ---------------------------------------------------------- conversaciones ----

function nuevaConversacion() {
  if (estado.enCurso) cancelarVerificacion();
  estado.turno = null;
  estado.conversacion = null; // el siguiente mensaje abre conversación nueva
  ui.conversacion.replaceChildren(ui.plantillaBienvenida.content.cloneNode(true));
  conectarEjemplos();
  marcarConversacionActiva(null);
  ui.entrada.value = "";
  ajustarAltura();
  ui.entrada.focus();
}

function quitarBienvenida() {
  ui.conversacion.querySelector(".bienvenida")?.remove();
}

async function abrirConversacion(id) {
  if (estado.enCurso) {
    avisar(t("esperaEnCurso"));
    return;
  }
  try {
    const respuesta = await fetch(`/api/conversacion/${id}`);
    const guardada = await respuesta.json();
    if (!respuesta.ok) throw new Error(guardada.error || respuesta.statusText);

    ui.conversacion.replaceChildren();
    for (const turno of guardada.turnos) {
      const nodo = crear("div", "turno");
      nodo.appendChild(crear("span", "chip-fecha", fechaCorta(turno.fecha)));
      nodo.appendChild(crear("div", "burbuja-usuario", turno.afirmacion));
      nodo.appendChild(renderInforme(turno.informe));
      ui.conversacion.appendChild(nodo);
    }
    estado.conversacion = id; // seguir escribiendo continúa este hilo
    marcarConversacionActiva(id);
    bajarConversacion();
    ui.entrada.focus();
  } catch (err) {
    avisar(t("noAbrir", err.message), true);
  }
}

function marcarConversacionActiva(id) {
  ui.listaConversaciones.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("activa", id !== null && li.dataset.id === String(id));
  });
}

// ------------------------------------------------------- envío y progreso ----

function enviarVerificacion() {
  const afirmacion = ui.entrada.value.trim();
  if (!afirmacion || !estado.conectado) return;
  if (estado.enCurso) return;

  // Nota: no se envía "preguntas": la búsqueda guiada por LLM es una
  // capacidad del agente — el servidor la activa si el modelo local existe.
  estado.ws.send(JSON.stringify({
    tipo: "verificar",
    afirmacion,
    lang: ui.idioma.value,
    memoria: ui.memoria.checked,
    tareas: ui.tareas.checked,
    modo: estado.modo,
    carpeta: estado.espacio || undefined,          // ausente = espacio General
    conversacion: estado.conversacion ?? undefined, // ausente = hilo nuevo
  }));

  quitarBienvenida();
  mostrarAdjunto("");

  const turno = crear("div", "turno");
  turno.appendChild(crear("div", "burbuja-usuario", afirmacion));
  const registro = crear("div", "registro");
  turno.appendChild(registro);
  ui.conversacion.appendChild(turno);

  estado.turno = { contenedor: turno, registro, pasos: 0 };
  estado.enCurso = true;
  ui.entrada.value = "";
  ajustarAltura();
  ui.enviar.textContent = "■";
  ui.enviar.title = t("detenerTitulo");
  ui.enviar.classList.add("detener");
  bajarConversacion();
}

function anotarProgreso(mensaje) {
  const turno = estado.turno;
  if (!turno) return;
  turno.registro.querySelector(".actual")?.classList.remove("actual");
  turno.registro.appendChild(crear("div", "actual", mensaje));
  turno.pasos++;
  turno.registro.scrollTop = turno.registro.scrollHeight;
  bajarConversacion();
}

function terminarTurno() {
  const turno = estado.turno;
  estado.enCurso = false;
  ui.enviar.textContent = "➤";
  ui.enviar.title = t("enviarTitulo");
  ui.enviar.classList.remove("detener");
  if (!turno) return;

  // El registro en vivo se pliega a un resumen expandible.
  turno.registro.querySelector(".actual")?.classList.remove("actual");
  const plegado = document.createElement("details");
  plegado.className = "registro-plegado";
  const resumen = crear("summary", null, t("verProceso", turno.pasos));
  plegado.appendChild(resumen);
  turno.registro.replaceWith(plegado);
  plegado.appendChild(turno.registro);
  estado.turno = null;
}

function cancelarVerificacion() {
  if (estado.conectado) estado.ws.send(JSON.stringify({ tipo: "cancelar" }));
}

// ---------------------------------------------------------------- permisos ----

function pedirPermiso(m) {
  const turno = estado.turno;
  if (!turno) return;

  const tarjeta = crear("div", "tarjeta-permiso");
  tarjeta.appendChild(crear("div", "permiso-titulo", t("permisoTitulo")));
  tarjeta.appendChild(crear("div", "permiso-detalle", m.detalle));
  const botones = crear("div", "permiso-botones");

  const responder = (aprobado, todo, etiqueta) => {
    estado.ws.send(JSON.stringify({
      tipo: "permiso_respuesta", id: m.id, aprobado, todo: Boolean(todo),
    }));
    tarjeta.classList.add("respondida");
    botones.querySelectorAll("button").forEach((b) => (b.disabled = true));
    tarjeta.appendChild(crear("div", "permiso-resultado", etiqueta));
  };

  const permitir = crear("button", "boton-primario", t("permitir"));
  permitir.onclick = () => responder(true, false, t("resPermitido"));
  const todo = crear("button", "boton-secundario", t("permitirTodo"));
  todo.title = t("permitirTodoTitulo");
  todo.onclick = () => responder(true, true, t("resPermitidoTodo"));
  const denegar = crear("button", "boton-peligro", t("denegar"));
  denegar.onclick = () => responder(false, false, t("resDenegado"));

  botones.append(permitir, todo, denegar);
  tarjeta.appendChild(botones);
  turno.contenedor.appendChild(tarjeta);
  bajarConversacion();
}

// ---------------------------------------------------------------- memoria ----

function mostrarMemoria(previas) {
  const turno = estado.turno;
  if (!turno || !previas?.length) return;
  const ultima = previas[0];
  const v = infoVeredicto(ultima.veredicto);
  const chip = crear("div", "chip-memoria", t(
    "chipMemoria",
    fechaCorta(ultima.fecha),
    v.titulo.toLowerCase(),
    Math.round(ultima.confianza * 100),
  ));
  turno.contenedor.insertBefore(chip, turno.registro);
  bajarConversacion();
}

// ---------------------------------------------------------------- informe ----

function renderRespuesta(texto) {
  // Answer text with ``` fences rendered as copyable code blocks (the
  // feature the 2026-07-16 screenshot asked for; classes live in estilo.css).
  const contenedor = crear("div", "respuesta-texto");
  const partes = String(texto).split(/```(?:[a-zA-Z]*\n)?/);
  partes.forEach((parte, indice) => {
    if (!parte.trim()) return;
    if (indice % 2 === 1) {
      const bloque = crear("div", "bloque-codigo");
      const pre = document.createElement("pre");
      pre.textContent = parte.replace(/\n$/, "");
      const boton = crear("button", "boton-copiar", "⧉");
      boton.title = "Copiar";
      boton.addEventListener("click", () => navigator.clipboard.writeText(pre.textContent));
      bloque.appendChild(boton);
      bloque.appendChild(pre);
      contenedor.appendChild(bloque);
    } else {
      contenedor.appendChild(crear("div", "", parte.trim()));
    }
  });
  return contenedor;
}

function renderInforme(informe) {
  // Una pregunta no se "refuta": el modo respuesta muestra el texto con sus
  // citas y NUNCA una etiqueta de veredicto (fallo medido 2026-07-16).
  if (informe.tipo === "pregunta" || informe.tipo === "tarea") {
    const tarjeta = crear("div", "tarjeta-veredicto veredicto-respuesta");
    tarjeta.appendChild(tituloVeredicto({
      titulo: t(informe.tipo === "tarea" ? "tarea" : "respuesta"),
    }));
    tarjeta.appendChild(renderRespuesta(informe.respuesta || ""));
    for (const hecho of informe.hechos || []) {
      tarjeta.appendChild(renderHecho(hecho, { sinVeredicto: true }));
    }
    return tarjeta;
  }

  const v = infoVeredicto(informe.veredicto);
  const tarjeta = crear("div", `tarjeta-veredicto ${v.clase}`);
  tarjeta.appendChild(tituloVeredicto(v));

  const barra = crear("div", "barra-confianza");
  const relleno = crear("div");
  relleno.style.width = `${Math.round(informe.confianza * 100)}%`;
  barra.appendChild(relleno);
  tarjeta.appendChild(barra);
  tarjeta.appendChild(crear(
    "div", "confianza-texto", t("confianza", Math.round(informe.confianza * 100))));

  if (informe.respuesta) {
    tarjeta.appendChild(renderRespuesta(informe.respuesta));
  }

  for (const hecho of informe.hechos || []) tarjeta.appendChild(renderHecho(hecho));
  return tarjeta;
}

function mostrarInforme(informe) {
  const turno = estado.turno;
  if (!turno) return;
  const contenedor = turno.contenedor;
  terminarTurno();
  contenedor.appendChild(renderInforme(informe));
  bajarConversacion();
  cargarConversaciones(); // la barra lateral recoge el turno recién guardado
}

function renderHecho(vh, opciones = {}) {
  const nodo = crear("div", "hecho");
  nodo.appendChild(crear("div", "hecho-texto", vh.hecho.texto));

  if (!opciones.sinVeredicto) {
    const v = infoVeredicto(vh.veredicto);
    const linea = crear("div", `hecho-veredicto ${v.clase}`);
    linea.appendChild(tituloVeredicto(v));
    linea.appendChild(crear("span", "confianza-texto", `· ${Math.round(vh.confianza * 100)}%`));
    nodo.appendChild(linea);
  }

  const evidencias = [
    ...(vh.a_favor || []).map((p) => ({ p, lado: "a-favor", clave: "aFavor" })),
    ...(vh.en_contra || []).map((p) => ({ p, lado: "en-contra", clave: "enContra" })),
  ];

  if (!evidencias.length) {
    nodo.appendChild(crear("div", "sin-evidencia", t("sinEvidencia")));
    return nodo;
  }

  // Las citas van plegadas por defecto en un desplegable.
  const aFavor = (vh.a_favor || []).length;
  const enContra = (vh.en_contra || []).length;
  const partes = [];
  if (aFavor) partes.push(t("aFavor", aFavor));
  if (enContra) partes.push(t("enContra", enContra));

  const citas = document.createElement("details");
  citas.className = "citas";
  citas.appendChild(crear(
    "summary", null, `${t("citas", evidencias.length)} · ${partes.join(" · ")}`));
  const lista = crear("ul", "evidencias");
  for (const e of evidencias) lista.appendChild(renderEvidencia(e));
  citas.appendChild(lista);
  nodo.appendChild(citas);
  return nodo;
}

function renderEvidencia({ p, lado, clave }) {
  const item = crear("li", "evidencia");
  const meta = crear("div", "evidencia-meta");
  // Etiqueta legible en cualquier idioma: se deriva del diccionario
  // («3 a favor» → «A favor», «3 dafür» → «Dafür»).
  const palabra = t(clave, "").trim();
  const texto = palabra.charAt(0).toUpperCase() + palabra.slice(1);
  meta.appendChild(crear("span", `evidencia-etiqueta ${lado}`, `${texto} ${Math.round(p.prob * 100)}%`));
  meta.appendChild(crear("span", null, p.evidencia.dominio));
  if (p.evidencia.idioma) meta.appendChild(crear("span", null, p.evidencia.idioma));
  item.appendChild(meta);

  const cuerpo = p.evidencia.texto.length > 280
    ? p.evidencia.texto.slice(0, 280) + "…"
    : p.evidencia.texto;
  item.appendChild(crear("div", "evidencia-texto", `«${cuerpo}»`));

  if (p.evidencia.url) {
    const enlace = crear("a", null, p.evidencia.titulo || p.evidencia.url);
    enlace.href = p.evidencia.url;
    enlace.target = "_blank";
    enlace.rel = "noopener noreferrer";
    item.appendChild(enlace);
  }
  return item;
}

function mostrarCancelado() {
  const turno = estado.turno;
  const contenedor = turno?.contenedor;
  terminarTurno();
  contenedor?.appendChild(crear("div", "nota-cancelado", t("cancelada")));
}

function mostrarError(mensaje) {
  const turno = estado.turno;
  if (turno) {
    const contenedor = turno.contenedor;
    terminarTurno();
    contenedor.appendChild(crear("div", "nota-error", mensaje));
    bajarConversacion();
  } else {
    avisar(mensaje, true);
  }
}

// -------------------------------------------------------------- documentos ----

function elegirTipoAdjunto(boton) {
  const tipo = boton.dataset.tipo;
  if (tipo === "imagen" && !estado.capacidades.imagen) {
    avisar(t("ocrFalta"), true);
    return;
  }
  if (tipo === "pdf" && !estado.capacidades.pdf) {
    avisar(t("pdfFalta"), true);
    return;
  }
  estado.tipoAdjunto = tipo;
  ui.selectorArchivo.accept = boton.dataset.accept;
  ui.menuAdjuntar.classList.add("oculto");
  ui.selectorArchivo.click();
}

async function procesarArchivo(archivo, tipo) {
  if (!archivo) return;
  tipo = tipo || estado.tipoAdjunto || (archivo.type.startsWith("image/") ? "imagen" : "texto");
  const esImagen = tipo === "imagen";
  const url = esImagen ? "/api/imagen" : "/api/documento";
  const nombre = archivo.name || (esImagen ? "imagen.png" : "documento");
  const icono = esImagen ? "🖼 " : "📄 ";

  mostrarAdjunto(icono + t("extrayendo", nombre));
  try {
    const datos = new FormData();
    datos.append("archivo", archivo, nombre);
    const respuesta = await fetch(url, { method: "POST", body: datos });
    const cuerpo = await respuesta.json();
    if (!respuesta.ok) throw new Error(cuerpo.error || respuesta.statusText);
    if (!cuerpo.texto) {
      mostrarAdjunto(icono + t("sinTextoLegible", nombre));
      return;
    }
    let texto = cuerpo.texto;
    let recorte = "";
    if (texto.length > MAX_TEXTO_DOCUMENTO) {
      texto = texto.slice(0, MAX_TEXTO_DOCUMENTO);
      recorte = t("recortado", MAX_TEXTO_DOCUMENTO);
    }
    insertarTexto(texto);
    mostrarAdjunto(icono + t("extraido", nombre, recorte));
  } catch (err) {
    mostrarAdjunto("");
    avisar(t("noLeer", nombre, err.message), true);
  } finally {
    estado.tipoAdjunto = null;
  }
}

function mostrarAdjunto(mensaje) {
  ui.avisoAdjunto.textContent = mensaje;
  ui.avisoAdjunto.classList.toggle("oculto", !mensaje);
}

function insertarTexto(texto) {
  if (!texto) return;
  const actual = ui.entrada.value.trim();
  ui.entrada.value = actual ? `${actual} ${texto}` : texto;
  ajustarAltura();
  ui.entrada.focus();
}

// ---------------------------------------------- conversaciones del espacio ----

async function cargarConversaciones() {
  try {
    const carpeta = encodeURIComponent(estado.espacio || "");
    const respuesta = await fetch(`/api/conversaciones?carpeta=${carpeta}&limite=40`);
    const { conversaciones } = await respuesta.json();
    ui.listaConversaciones.replaceChildren();
    if (!conversaciones.length) {
      ui.listaConversaciones.appendChild(
        crear("li", "historial-vacio", t("sinConversaciones")));
      return;
    }
    for (const fila of conversaciones) {
      const item = crear("li");
      item.dataset.id = String(fila.id);
      item.appendChild(crear("span", "historial-afirmacion", fila.titulo || t("sinTitulo")));
      item.appendChild(crear("span", "historial-meta",
        `${t("turnos", fila.turnos)} · ${fechaCorta(fila.ultima)}`));
      item.title = t("reabrir");
      item.onclick = () => abrirConversacion(fila.id);
      item.classList.toggle("activa", estado.conversacion === fila.id);
      ui.listaConversaciones.appendChild(item);
    }
  } catch {
    /* la memoria es opcional: sin ella la lista simplemente queda vacía */
  }
}

// ---------------------------------------------------------------- entrada ----

function ajustarAltura() {
  ui.entrada.style.height = "auto";
  ui.entrada.style.height = `${Math.min(ui.entrada.scrollHeight, 160)}px`;
}

function conectarEjemplos() {
  ui.conversacion.querySelectorAll(".ejemplo").forEach((boton) => {
    boton.addEventListener("click", () => {
      ui.entrada.value = boton.textContent;
      ajustarAltura();
      ui.entrada.focus();
    });
  });
}

ui.entrada.addEventListener("input", ajustarAltura);

ui.entrada.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!estado.enCurso) enviarVerificacion();
  }
});

ui.entrada.addEventListener("paste", (e) => {
  const imagen = Array.from(e.clipboardData?.items || []).find((i) => i.type.startsWith("image/"));
  if (imagen) {
    e.preventDefault();
    procesarArchivo(imagen.getAsFile(), "imagen");
  }
});

document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  const archivo = e.dataTransfer?.files?.[0];
  if (!archivo) return;
  if (archivo.type.startsWith("image/")) procesarArchivo(archivo, "imagen");
  else if (archivo.name?.toLowerCase().endsWith(".pdf")) procesarArchivo(archivo, "pdf");
  else procesarArchivo(archivo, "texto");
});

ui.enviar.addEventListener("click", () => {
  if (estado.enCurso) cancelarVerificacion();
  else enviarVerificacion();
});

ui.adjuntar.addEventListener("click", (e) => {
  e.stopPropagation();
  ui.menuAdjuntar.classList.toggle("oculto");
});

ui.menuAdjuntar.querySelectorAll(".menu-opcion").forEach((boton) => {
  boton.addEventListener("click", () => elegirTipoAdjunto(boton));
});

ui.selectorArchivo.addEventListener("change", () => {
  procesarArchivo(ui.selectorArchivo.files?.[0]);
  ui.selectorArchivo.value = "";
});

ui.nuevaVerificacion.addEventListener("click", nuevaConversacion);

// ------------------------------------------------------------------ inicio ----

async function cargarCapacidades() {
  try {
    const respuesta = await fetch("/api/capacidades");
    estado.capacidades = await respuesta.json();
    ui.acercaVersion.textContent = estado.capacidades.version || "—";
  } catch {
    /* sin capacidades opcionales; los botones lo explican al usarse */
  }
}

async function iniciar() {
  cargarPreferencias();
  ui.conversacion.appendChild(ui.plantillaBienvenida.content.cloneNode(true));
  conectarEjemplos();
  aplicarIdioma();
  conectar();
  cargarCapacidades();
  ui.entrada.focus();
}

iniciar();
