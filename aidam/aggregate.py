"""Comparative logic aggregator (Module 4).

Explicit, auditable math — no neural network, on purpose. Combines the
per-pair judgements into a per-fact verdict, and the per-fact verdicts into
the verdict for the whole claim.

Independence and reliability rules (each one born from a measured failure):
1. Each domain contributes a single voice per side (its best evidence). A
   hundred pages copying the same press release don't weigh more than one
   source.
2. Reliability priors per source type: professional fact-checkers,
   encyclopedias, academia and official bodies weigh more than an unknown
   domain. Motivated by AVeriTeC: without this, the viral lie repeated on
   many sites beats the fact-checker that debunks it.
3. Echo is not evidence: a web snippet that merely repeats the claim almost
   word for word contributes no information of its own — supporting is not
   repeating. (Applies only to the supporting side: refuting requires
   original content.)
"""

from __future__ import annotations

import re

from .models import (
    EtiquetaPar,
    Evidencia,
    HechoAtomico,
    Informe,
    Veredicto,
    VeredictoHecho,
    VeredictoPar,
)

# Minimum probability for a judgement to count as signal.
UMBRAL_SENAL = 0.60
# How much one side's signal must exceed the other's to dominate;
# below this, the verdict is "conflicting evidence".
DOMINANCIA = 2.0
# Independent sources required for full confidence.
FUENTES_PLENAS = 3

# ── Reliability priors (transparent and debatable in the repo) ──
# Professional fact-checkers (IFCN network members/affiliates).
VERIFICADORES = {
    "politifact.com", "snopes.com", "factcheck.org", "fullfact.org",
    "chequeado.com", "maldita.es", "newtral.es", "factual.afp.com",
    "factcheck.afp.com", "leadstories.com", "checkyourfact.com",
    "boomlive.in", "altnews.in", "colombiacheck.com", "verificado.com.mx",
    "aosfatos.org", "lupa.uol.com.br", "correctiv.org", "pagellapolitica.it",
    "africacheck.org", "teyit.org", "faktisk.no", "demagog.org.pl",
    "verafiles.org", "factcheckni.org",
}
# A professional debunk is worth ~an order of magnitude more than the claim
# of an unknown domain: at 8.0, one fact-checker beats 3 viral sites, but
# 6+ independent sites still force "conflicting".
PESO_VERIFICADOR = 8.0
# Official documentation is the "fact-checker" of technical matters: for a
# claim about AWS or Python, docs.aws.amazon.com/docs.python.org is the
# certified source — it weighs as much as a professional fact-checker.
PESO_DOCS_OFICIALES = 8.0  # fuente == "docs-oficiales"
PESO_ENCICLOPEDIA = 2.5  # *.wikipedia.org
PESO_ACADEMICO = 2.5  # papers (fuente == "academica")
PESO_OFICIAL = 2.0  # .gov / .edu domains
PESO_WIKINEWS = 1.5
PESO_BASE = 1.0
PESO_ECO = 0.3  # multiplier for echo (rule 3)
_UMBRAL_ECO = 0.8  # fraction of claim words present in the passage

# Rule 4 — the attribution trap (measured on AVeriTeC v8: 18 refuted claims
# read as supported): a passage that "supports" but carries debunk or dubious
# attribution markers ("purportedly", "hoax", "fact check"…) is almost always
# an article that DESCRIBES the hoax, not one that asserts it. Textual NLI
# falls into the trap; the discount disarms it.
# Only unambiguous debunk markers: "fact check" and "rumor" were removed
# because a fact-check also CONFIRMS (measured in v9: Supported F1 dropped
# to 0.255 from discounting legitimate support).
_MARCADORES_DESMENTIDO = re.compile(
    r"\b(false(ly)?|falso|falsa(mente)?|hoax|bulo|debunk\w*|misleading"
    r"|no (real )?evidence|sin evidencia|desmentid\w*|desinformaci[oó]n|purported\w*"
    r"|supuesta(mente)?|alegada(mente)?|alleged(ly)?|den(y|ies|ied)|viral claim"
    r"|enga[ñn]os\w*)\b",
    re.IGNORECASE,
)
PESO_DESMENTIDO = 0.25


def peso_fuente(evidencia: Evidencia) -> float:
    """Reliability prior of the domain. Explicit so it can be audited."""
    dominio = evidencia.dominio
    if dominio in VERIFICADORES:
        return PESO_VERIFICADOR
    if evidencia.fuente == "docs-oficiales":
        return PESO_DOCS_OFICIALES
    if dominio.endswith((".wikipedia.org", ".wikiquote.org")) or dominio == "wikidata.org":
        return PESO_ENCICLOPEDIA
    if evidencia.fuente == "academica":
        return PESO_ACADEMICO
    if dominio.endswith((".gov", ".edu")) or ".gov." in dominio or ".edu." in dominio:
        return PESO_OFICIAL
    if evidencia.fuente == "wikinews":
        return PESO_WIKINEWS
    return PESO_BASE


_MIN_PALABRAS_ECO = 6


def _es_eco(hecho: HechoAtomico, evidencia: Evidencia) -> bool:
    """Does the passage merely repeat the claim without content of its own?

    Applies only to long, specific claims (≥6 content words, the profile of
    a viral claim). For short technical claims («Python lists are mutable»)
    any legitimate passage on the topic contains all the words — that is
    coverage, not echo.
    """
    palabras = set(re.findall(r"\w{4,}", hecho.texto.lower()))
    if len(palabras) < _MIN_PALABRAS_ECO:
        return False
    presentes = sum(1 for p in palabras if p in evidencia.texto.lower())
    return presentes / len(palabras) >= _UMBRAL_ECO


def _peso(par: VeredictoPar) -> float:
    """Total weight of a judgement: reliability prior × echo penalty."""
    peso = peso_fuente(par.evidencia)
    if par.etiqueta is EtiquetaPar.SUSTENTA:
        if par.evidencia.fuente in ("web", "desmentidos") and _es_eco(par.hecho, par.evidencia):
            peso *= PESO_ECO
        if _MARCADORES_DESMENTIDO.search(par.evidencia.texto):
            peso *= PESO_DESMENTIDO
    return peso


def _mejor_por_dominio(pares: list[VeredictoPar]) -> dict[str, VeredictoPar]:
    """One domain, one voice: its judgement with the highest weighted signal.

    If the same site has passages on both sides (typical of a fact-check,
    which narrates the myth before debunking it), it votes only with its
    strongest signal — its actual stance — instead of being counted twice.
    """
    mejores: dict[str, VeredictoPar] = {}
    for par in pares:
        if par.etiqueta is EtiquetaPar.NO_CONCLUYE or par.prob < UMBRAL_SENAL:
            continue
        clave = par.evidencia.dominio
        if clave not in mejores or par.prob * _peso(par) > mejores[clave].prob * _peso(
            mejores[clave]
        ):
            mejores[clave] = par
    return mejores


def _hay_voz_fiable(pares: list[VeredictoPar]) -> bool:
    """Does the side include at least one source with a high reliability prior?

    NLI probability is useless here: viral sites support at 95-99%.
    Reliability comes from the source type, not from judgement confidence.
    """
    return any(peso_fuente(p.evidencia) >= PESO_OFICIAL for p in pares)


def agregar_hecho(hecho: HechoAtomico, pares: list[VeredictoPar]) -> VeredictoHecho:
    """Aggregates the per-pair judgements into a verdict for the fact."""
    voces = _mejor_por_dominio(pares)
    a_favor = sorted(
        (p for p in voces.values() if p.etiqueta is EtiquetaPar.SUSTENTA),
        key=lambda p: p.prob,
        reverse=True,
    )
    en_contra = sorted(
        (p for p in voces.values() if p.etiqueta is EtiquetaPar.REFUTA),
        key=lambda p: p.prob,
        reverse=True,
    )
    senal_favor = sum(p.prob * _peso(p) for p in a_favor)
    senal_contra = sum(p.prob * _peso(p) for p in en_contra)
    total = senal_favor + senal_contra
    cobertura = min(1.0, len(voces) / FUENTES_PLENAS)

    if total == 0:
        veredicto, confianza = Veredicto.INSUFICIENTE, 0.0
    elif senal_favor > 0 and senal_contra > 0 and (
        max(senal_favor, senal_contra) < DOMINANCIA * min(senal_favor, senal_contra)
    ):
        # Tie zone: reliability breaks the tie. Real conflict = credible
        # evidence on BOTH sides; web noise tying with a credible debunk is
        # not conflict (measured on AVeriTeC: 13 of 16 predicted
        # "conflicting" were actually refuted through that pattern).
        fiable_favor = _hay_voz_fiable(a_favor)
        fiable_contra = _hay_voz_fiable(en_contra)
        if fiable_favor and fiable_contra:
            veredicto, confianza = Veredicto.CONTRADICTORIO, cobertura
        elif fiable_favor:
            veredicto = Veredicto.SUSTENTADO
            confianza = (senal_favor / total) * cobertura
        elif fiable_contra:
            veredicto = Veredicto.REFUTADO
            confianza = (senal_contra / total) * cobertura
        elif senal_favor > senal_contra:
            veredicto = Veredicto.SUSTENTADO
            confianza = (senal_favor / total) * cobertura
        else:
            veredicto = Veredicto.REFUTADO
            confianza = (senal_contra / total) * cobertura
    elif senal_favor > senal_contra:
        veredicto = Veredicto.SUSTENTADO
        confianza = (senal_favor / total) * cobertura
    else:
        veredicto = Veredicto.REFUTADO
        confianza = (senal_contra / total) * cobertura

    return VeredictoHecho(
        hecho=hecho,
        veredicto=veredicto,
        confianza=round(confianza, 3),
        a_favor=a_favor,
        en_contra=en_contra,
    )


def agregar_informe(afirmacion: str, hechos: list[VeredictoHecho]) -> Informe:
    """Combines the per-fact verdicts into the verdict for the claim.

    A claim is only as true as its weakest fact: any refuted fact refutes
    the whole; any contradiction or gap prevents declaring it supported.
    """
    veredictos = {h.veredicto for h in hechos}
    if Veredicto.REFUTADO in veredictos:
        global_ = Veredicto.REFUTADO
        relevantes = [h for h in hechos if h.veredicto is Veredicto.REFUTADO]
    elif Veredicto.CONTRADICTORIO in veredictos:
        global_ = Veredicto.CONTRADICTORIO
        relevantes = [h for h in hechos if h.veredicto is Veredicto.CONTRADICTORIO]
    elif Veredicto.INSUFICIENTE in veredictos:
        global_ = Veredicto.INSUFICIENTE
        relevantes = [h for h in hechos if h.veredicto is Veredicto.INSUFICIENTE]
    else:
        global_ = Veredicto.SUSTENTADO
        relevantes = hechos

    confianza = (
        round(min(h.confianza for h in relevantes), 3) if relevantes else 0.0
    )
    return Informe(
        afirmacion=afirmacion,
        veredicto=global_,
        confianza=confianza,
        hechos=hechos,
    )
