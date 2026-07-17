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


def es_seguimiento(texto: str) -> bool:
    limpio = texto.strip()
    if _CONECTORES.match(limpio):
        return True
    return len(limpio) < 60 and bool(_DEICTICOS.search(limpio))


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

    def _codificar(self, textos: list[str]):
        from ..vectores import _codificador

        return _codificador()(textos)

    def agregar(self, pregunta: str) -> None:
        self.turnos.append(pregunta)
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
