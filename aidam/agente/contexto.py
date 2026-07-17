"""Conversational context: follow-up questions become self-contained.

Measured product failure (2026-07-16, Jeffrey's screenshot): after asking
about LoRa, the follow-up «¿y en el contexto de machine learning y
modelos?» was treated as a brand-new question and answered with generic
ML fluff. Standard conversational-RAG fix, in its LIGHTEST form: detect
the follow-up, rewrite it self-contained by carrying over the previous
turn's topic terms — pure string work, zero models, microseconds. The
optional narrator LLM may produce a finer rewrite when loaded; the
heuristic is the always-available floor (the same two-layer contract as
respuesta_concisa).

The rewritten question is always SHOWN to the user («pregunta
interpretada: …») — context resolution must be transparent, never a
silent guess.
"""

from __future__ import annotations

import re
import unicodedata

# Connector openings that mark a follow-up rather than a fresh question.
_CONECTORES = re.compile(
    r"^\s*¿?\s*(y|pero|entonces|adem[aá]s|o sea|and|but|so|also)\b"
    r"|^\s*¿?\s*(en|dentro de) (el|ese|este|dicho) (contexto|caso|sentido)\b"
    r"|^\s*¿?\s*(qu[eé] tal|y si)\b",
    re.IGNORECASE,
)
# Deictics that need an antecedent from the previous turn.
_DEICTICOS = re.compile(
    r"\b(eso|esto|aquello|ese|esa|este|esta|[eé]l|ella|ellos|ellas|ah[ií]"
    r"|that|this|it|there)\b",
    re.IGNORECASE,
)
_VACIAS = {
    "para", "como", "cómo", "donde", "dónde", "cuando", "cuándo", "cual",
    "cuál", "quien", "quién", "sobre", "entre", "hasta", "desde", "porque",
    "aunque", "según", "segun", "sirve", "funciona", "significa", "contexto",
    "what", "where", "when", "which", "about", "does", "mean", "work",
}


def _terminos_clave(texto: str, maximo: int = 4) -> list[str]:
    """Content words that name the previous turn's topic."""
    palabras = re.findall(r"[\wáéíóúñÁÉÍÓÚÑ]{4,}", texto)
    claves, vistas = [], set()
    for p in palabras:
        plano = unicodedata.normalize("NFKD", p.casefold())
        plano = "".join(c for c in plano if not unicodedata.combining(c))
        if plano in _VACIAS or plano in vistas:
            continue
        vistas.add(plano)
        claves.append(p)
        if len(claves) == maximo:
            break
    return claves


_RECHAZOS = re.compile(
    r"^\s*¿?\s*(no[,.]?\s*(no\s*)?(es|era)\s*(esa?|ese|eso)?|esa? no|ese no"
    r"|otra( vez)?|dame otra|busca otra|not (that|this) one|another one|wrong)\s*[\.\!\?]*\s*$",
    re.IGNORECASE,
)


def es_rechazo(texto: str) -> bool:
    """Is the input a rejection of the previous answer, not a new claim?

    Measured product failure (2026-07-16): «no, no es esa» was verified
    as a claim — REFUTED 92% with Russian grammar evidence about
    'ese/esa'. A rejection is a dialogue act: the right response is the
    NEXT-best answer with the rejected source excluded, never a verdict.
    """
    return len(texto.strip()) < 40 and bool(_RECHAZOS.match(texto.strip()))


_SOCIALES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*(hola|buenas( noches| tardes| d[ií]as)?|hey|hi|hello)\s*[\.\!]*\s*$", re.I),
     "¡Hola! Dime una afirmación para verificar o una pregunta para investigar."),
    (re.compile(r"^\s*(gracias|muchas gracias|thank you|thanks|ty)\s*[\.\!]*\s*$", re.I),
     "De nada. Aquí sigo para la próxima verificación."),
    (re.compile(r"^\s*(ok(ay)?|vale|perfecto|genial|entendido|listo|good|great|nice)\s*[\.\!]*\s*$", re.I),
     "Perfecto. ¿Verificamos algo más?"),
    (re.compile(r"^\s*(adi[oó]s|hasta luego|chao|bye|nos vemos)\s*[\.\!]*\s*$", re.I),
     "Hasta luego. La memoria guarda lo verificado para la próxima sesión."),
    (re.compile(r"^\s*¿?\s*(qui[eé]n eres|qu[eé] puedes hacer|what can you do|who are you)\s*\??\s*$", re.I),
     "Soy AIDAM: verifico afirmaciones contra evidencia de fuentes abiertas, "
     "respondo preguntas de investigación citando de dónde sale cada dato, y "
     "comparo código midiéndolo de verdad. Nada de opiniones: evidencia."),
]


def respuesta_social(texto: str) -> str | None:
    """Conversational acts get conversational replies — and only they do.

    Jeffrey's requirement (2026-07-16): the agent should talk like a
    person when the input is social, and know exactly WHEN that applies.
    Detection is rule-based and closed (greetings, thanks, acks,
    farewells, who-are-you): everything else keeps flowing to the
    verification/question paths. The narrator LLM may phrase it warmer
    when loaded; this deterministic floor is always there.
    """
    limpio = texto.strip()
    if len(limpio) > 40:
        return None
    for patron, respuesta in _SOCIALES:
        if patron.match(limpio):
            return respuesta
    return None


def es_seguimiento(texto: str) -> bool:
    limpio = texto.strip()
    if _CONECTORES.match(limpio):
        return True
    return len(limpio) < 60 and bool(_DEICTICOS.search(limpio))


class GrafoPalabras:
    """Jeffrey's architecture (2026-07-16): keywords as interned IDs nested
    to their contexts — the keyword-graph branch of 2025-26 agent memory
    (Zep/Graphiti-style, in miniature). Each normalized word is stored
    ONCE and gets an integer id; every turn is just a tuple of ids (bytes,
    not text — his «desglosar palabras ahorrando contexto»); the inverted
    index word→turns is the graph's edges. Lookup weights words by rarity
    (a word that appeared in one turn pinpoints it; one in every turn says
    nothing), so «volviendo a la muralla» finds the muralla turn by EXACT
    match at zero model cost — complementing, not replacing, the
    embedding path (which catches synonyms)."""

    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self._palabras: list[str] = []
        self._turnos: list[tuple[int, ...]] = []
        self._por_palabra: dict[int, list[int]] = {}

    def _id(self, palabra: str) -> int:
        plano = unicodedata.normalize("NFKD", palabra.casefold())
        plano = "".join(c for c in plano if not unicodedata.combining(c))
        if plano not in self._ids:
            self._ids[plano] = len(self._palabras)
            self._palabras.append(plano)
        return self._ids[plano]

    def agregar(self, texto: str) -> None:
        ids = tuple(self._id(t) for t in _terminos_clave(texto, maximo=8))
        indice = len(self._turnos)
        self._turnos.append(ids)
        for i in set(ids):
            self._por_palabra.setdefault(i, []).append(indice)

    def buscar(self, texto: str) -> tuple[str, float] | None:
        """Best prior turn by rarity-weighted keyword overlap."""
        if not self._turnos:
            return None
        puntajes: dict[int, float] = {}
        for t in _terminos_clave(texto, maximo=8):
            plano = unicodedata.normalize("NFKD", t.casefold())
            plano = "".join(c for c in plano if not unicodedata.combining(c))
            i = self._ids.get(plano)
            if i is None:
                continue
            apariciones = self._por_palabra.get(i, [])
            peso = 1.0 / len(apariciones) if apariciones else 0.0
            for turno in apariciones:
                puntajes[turno] = puntajes.get(turno, 0.0) + peso
        if not puntajes:
            return None
        mejor = max(puntajes, key=puntajes.get)
        reconstruido = " ".join(self._palabras[i] for i in self._turnos[mejor])
        return reconstruido, puntajes[mejor]


class ContextoConversacion:
    """Multi-turn conversational state — RAM only, dies with the session.

    Jeffrey's requirements (2026-07-16): follow-ups may point several
    turns back («volviendo a lo de la muralla…»), the mechanism must be
    light, and context is temporary state — it never touches the repo or
    disk. How the big systems do it, in miniature: recency is the default
    antecedent, but every turn is embedded once (computed-once e5, CPU)
    and a follow-up that semantically matches an OLDER turn resolves
    against that turn instead. Without the embedder, graceful recency-only.
    """

    _MAX_TURNOS = 20
    _MAX_COMPACTADOS = 200  # compacted turns: terms + embedding, no full text
    _UMBRAL_ANTECEDENTE = 0.82  # must beat the recency default clearly

    def __init__(self) -> None:
        self.turnos: list[str] = []
        self._vectores: list = []  # one embedding per turn (lazy, best effort)
        # Tier 2 (2025-26 consensus: verbatim window + anchored incremental
        # summary + retrieval store — arXiv:2308.15022 recursive dialogue
        # memory; Mem0/MemGPT tiering). Evicted turns FOLD here instead of
        # vanishing: topic terms + embedding survive (a few hundred bytes),
        # full text does not — genuine compaction, threshold-triggered.
        self._compactados: list[tuple[str, object]] = []  # (términos, vector)
        # Keyword graph (Jeffrey's architecture): exact rare-word recall at
        # zero model cost, covering EVERY turn ever seen this session.
        self.grafo = GrafoPalabras()

    def _codificar(self, textos: list[str]):
        from ..vectores import _codificador

        return _codificador()(textos)

    def agregar(self, pregunta: str) -> None:
        self.turnos.append(pregunta)
        self.grafo.agregar(pregunta)
        try:
            self._vectores.append(self._codificar([f"query: {pregunta}"])[0])
        except Exception:
            self._vectores.append(None)
        if len(self.turnos) > self._MAX_TURNOS:
            texto = self.turnos.pop(0)
            vector = self._vectores.pop(0)
            self._compactados.append((" ".join(_terminos_clave(texto)), vector))
            if len(self._compactados) > self._MAX_COMPACTADOS:
                self._compactados.pop(0)

    def resumen(self) -> str:
        """Anchored rolling summary of everything outside the verbatim
        window — term-level, deterministic, always available (the narrator
        LLM can produce finer prose from it, never replace it)."""
        return "; ".join(t for t, _ in self._compactados if t)

    def _antecedente(self, entrada: str) -> str | None:
        """Most recent turn by default; an older (or compacted-out) turn
        if it matches the follow-up's meaning clearly better."""
        if not self.turnos:
            return None
        eleccion = self.turnos[-1]
        # Keyword graph first: an exact rare-word hit («muralla», «LoRA»)
        # pinpoints the antecedent at zero model cost. Score >= 0.5 means
        # at least one word that appears in very few turns matched.
        exacto = self.grafo.buscar(entrada)
        if exacto is not None and exacto[1] >= 0.5:
            return exacto[0]
        try:
            consulta = self._codificar([f"query: {entrada}"])[0]
            mejor, mejor_p = None, self._UMBRAL_ANTECEDENTE
            candidatos = list(zip(self.turnos[:-1], self._vectores[:-1]))
            candidatos += [(terminos, v) for terminos, v in self._compactados]
            for turno, vector in candidatos:
                if vector is None or not turno:
                    continue
                p = float(vector @ consulta)
                if p > mejor_p:
                    mejor, mejor_p = turno, p
            if mejor is not None:
                eleccion = mejor
        except Exception:
            pass
        return eleccion

    def resolver(self, entrada: str) -> str:
        """Self-contained rewrite against the best antecedent turn."""
        resuelta = resolver_seguimiento(entrada, self._antecedente(entrada))
        self.agregar(resuelta)
        return resuelta


def resolver_seguimiento(entrada: str, pregunta_previa: str | None) -> str:
    """Returns the self-contained question (or the input untouched).

    Heuristic carry-over: the previous turn's topic terms that the
    follow-up doesn't already mention are prepended, and the leading
    connector is dropped: («que es lora?», «y en el contexto de machine
    learning?») → «lora — en el contexto de machine learning?».
    """
    if not pregunta_previa or not es_seguimiento(entrada):
        return entrada
    tema = [
        t for t in _terminos_clave(pregunta_previa)
        if t.casefold() not in entrada.casefold()
    ]
    if not tema:
        return entrada
    cuerpo = _CONECTORES.sub("", entrada.strip(), count=1).strip(" ,;")
    cuerpo = cuerpo or entrada.strip()
    resuelta = f"{' '.join(tema)} — {cuerpo}"
    return resuelta if resuelta.endswith("?") or not entrada.strip().endswith("?") else resuelta + "?"
