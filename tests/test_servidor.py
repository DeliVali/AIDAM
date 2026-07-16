"""Tests of the interface server: WS protocol, permission gate, endpoints.

Everything runs offline: a fake `verificar_fn` honours the pipeline contract
(progreso callback + injected retriever) and `recuperar_fn` replaces live
retrieval behind the permission gate, so the tests exercise the protocol,
not the models or the network.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from aidam.models import (  # noqa: E402
    EtiquetaPar,
    Evidencia,
    HechoAtomico,
    Informe,
    Veredicto,
    VeredictoHecho,
    VeredictoPar,
)
from aidam.servidor import crear_app  # noqa: E402


def _evidencia_falsa(hecho: HechoAtomico) -> Evidencia:
    return Evidencia(
        texto="La Torre Eiffel se encuentra en París, Francia.",
        url="https://es.wikipedia.org/wiki/Torre_Eiffel",
        titulo="Torre Eiffel",
        dominio="es.wikipedia.org",
        fuente="wikipedia",
        idioma="es",
    )


def _verificar_falso(
    afirmacion,
    *,
    lang="es",
    max_idiomas=5,
    preguntas=False,
    progreso=None,
    recuperador=None,
    buscador_preguntas=None,
    **_ignorados,
):
    """Same contract as pipeline.verificar: one fact per line of the claim,
    evidence via the injected (gated) retriever."""
    hechos = [
        HechoAtomico(texto=linea.strip(), origen=afirmacion)
        for linea in afirmacion.splitlines()
        if linea.strip()
    ]
    progreso(f"Afirmación descompuesta en {len(hechos)} hecho(s) atómico(s)")

    veredictos = []
    for hecho in hechos:
        evidencias = recuperador(hecho, lang=lang, max_idiomas=max_idiomas, categoria=None)
        if evidencias:
            par = VeredictoPar(hecho, evidencias[0], EtiquetaPar.SUSTENTA, 0.97)
            veredictos.append(
                VeredictoHecho(hecho, Veredicto.SUSTENTADO, 0.97, a_favor=[par])
            )
        else:
            veredictos.append(VeredictoHecho(hecho, Veredicto.INSUFICIENTE, 0.0))

    if all(v.veredicto is Veredicto.INSUFICIENTE for v in veredictos):
        return Informe(afirmacion, Veredicto.INSUFICIENTE, 0.0, veredictos)
    return Informe(afirmacion, Veredicto.SUSTENTADO, 0.97, veredictos)


def _recuperar_falso(hecho, lang="es", max_idiomas=5, categoria=None):
    return [_evidencia_falsa(hecho)]


@pytest.fixture()
def cliente(tmp_path):
    app = crear_app(
        verificar_fn=_verificar_falso,
        ruta_memoria=str(tmp_path / "memoria.db"),
        recuperar_fn=_recuperar_falso,
    )
    with TestClient(app) as cliente:
        yield cliente


def _enviar(ws, **mensaje):
    ws.send_text(json.dumps(mensaje))


def _recibir(ws):
    return json.loads(ws.receive_text())


def _recibir_hasta(ws, tipo, saltando=("progreso", "memoria")):
    """Skips intermediate events until `tipo` arrives (fails on anything else)."""
    for _ in range(50):
        mensaje = _recibir(ws)
        if mensaje["tipo"] == tipo:
            return mensaje
        assert mensaje["tipo"] in saltando, f"evento inesperado: {mensaje}"
    raise AssertionError(f"nunca llegó el evento {tipo!r}")


# ---- endpoints HTTP ----------------------------------------------------------


def test_capacidades(cliente):
    datos = cliente.get("/api/capacidades").json()
    assert isinstance(datos["voz"], bool)
    assert isinstance(datos["imagen"], bool)
    assert isinstance(datos["pdf"], bool)
    assert datos["version"]


def test_fuentes_lista_el_registro(cliente):
    fuentes = cliente.get("/api/fuentes").json()["fuentes"]
    assert len(fuentes) >= 10
    assert all({"nombre", "descripcion", "categorias"} <= set(f) for f in fuentes)


def test_documento_texto_plano(cliente):
    respuesta = cliente.post(
        "/api/documento",
        files={"archivo": ("nota.txt", "La Torre Eiffel está en París".encode(), "text/plain")},
    )
    assert respuesta.status_code == 200
    assert "Eiffel" in respuesta.json()["texto"]


def test_documento_pdf_en_blanco(cliente):
    pypdf = pytest.importorskip("pypdf")
    import io as _io

    escritor = pypdf.PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    tampon = _io.BytesIO()
    escritor.write(tampon)
    respuesta = cliente.post(
        "/api/documento",
        files={"archivo": ("doc.pdf", tampon.getvalue(), "application/pdf")},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["texto"] == ""  # página en blanco: sin texto, sin error


def test_documento_pdf_sin_dependencia_da_501(cliente, monkeypatch):
    import aidam.servidor as servidor

    monkeypatch.setattr(servidor.importlib.util, "find_spec", lambda _n: None)
    respuesta = cliente.post(
        "/api/documento", files={"archivo": ("doc.pdf", b"%PDF-1.4", "application/pdf")}
    )
    assert respuesta.status_code == 501
    assert "PDF" in respuesta.json()["error"]


def test_index_sirve_la_interfaz(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "AIDAM" in respuesta.text


def test_imagen_sin_dependencia_da_501(cliente, monkeypatch):
    import aidam.servidor as servidor

    monkeypatch.setattr(servidor.importlib.util, "find_spec", lambda _n: None)
    respuesta = cliente.post("/api/imagen", files={"archivo": ("x.png", b"\x89PNG", "image/png")})
    assert respuesta.status_code == 501
    assert "imagen" in respuesta.json()["error"]


def test_voz_sin_dependencia_da_501(cliente, monkeypatch):
    import aidam.servidor as servidor

    monkeypatch.setattr(servidor.importlib.util, "find_spec", lambda _n: None)
    respuesta = cliente.post("/api/voz", files={"archivo": ("x.webm", b"00", "audio/webm")})
    assert respuesta.status_code == 501
    assert "voz" in respuesta.json()["error"]


# ---- protocolo WebSocket -----------------------------------------------------


def test_modo_auto_devuelve_informe_con_citas(cliente):
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion="La Torre Eiffel está en París", modo="auto")
        informe = _recibir_hasta(ws, "informe")["informe"]
    assert informe["veredicto"] == "sustentado"
    assert informe["hechos"][0]["a_favor"][0]["etiqueta"] == "sustenta"
    assert informe["hechos"][0]["a_favor"][0]["evidencia"]["dominio"] == "es.wikipedia.org"


def test_afirmacion_vacia_da_error(cliente):
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion="   ")
        assert _recibir(ws)["tipo"] == "error"


def test_modo_permisos_pide_antes_de_buscar(cliente):
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion="Una afirmación", modo="permisos")
        permiso = _recibir_hasta(ws, "permiso")
        assert permiso["accion"] == "buscar_evidencia"
        assert "Una afirmación" in permiso["detalle"]
        _enviar(ws, tipo="permiso_respuesta", id=permiso["id"], aprobado=True)
        informe = _recibir_hasta(ws, "informe")["informe"]
    assert informe["veredicto"] == "sustentado"


def test_denegar_omite_la_busqueda(cliente):
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion="Una afirmación", modo="permisos")
        permiso = _recibir_hasta(ws, "permiso")
        _enviar(ws, tipo="permiso_respuesta", id=permiso["id"], aprobado=False)
        informe = _recibir_hasta(ws, "informe")["informe"]
    # Sin evidencia (búsqueda denegada) el hecho queda insuficiente.
    assert informe["veredicto"] == "evidencia_insuficiente"
    assert informe["hechos"][0]["a_favor"] == []


def test_permitir_todo_no_vuelve_a_preguntar(cliente):
    with cliente.websocket_connect("/ws") as ws:
        _enviar(
            ws,
            tipo="verificar",
            afirmacion="Primer hecho\nSegundo hecho",  # dos hechos → dos búsquedas
            modo="permisos",
        )
        permiso = _recibir_hasta(ws, "permiso")
        _enviar(ws, tipo="permiso_respuesta", id=permiso["id"], aprobado=True, todo=True)
        # La segunda búsqueda ya no pide permiso: lo siguiente es el informe.
        informe = _recibir_hasta(ws, "informe")["informe"]
    assert len(informe["hechos"]) == 2
    assert all(h["veredicto"] == "sustentado" for h in informe["hechos"])


def test_memoria_guarda_y_avisa_de_repetidas(cliente):
    afirmacion = "La Torre Eiffel está en París"
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion=afirmacion)
        _recibir_hasta(ws, "informe")

    historial = cliente.get("/api/historial").json()["historial"]
    assert len(historial) == 1
    assert historial[0]["afirmacion"] == afirmacion
    assert historial[0]["veredicto"] == "sustentado"

    # Segunda verificación de la MISMA afirmación: avisa de la previa…
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion=afirmacion)
        memoria = _recibir_hasta(ws, "memoria", saltando=("progreso",))
        assert memoria["previas"][0]["veredicto"] == "sustentado"
        # …y aún así se vuelve a verificar (el informe llega igualmente).
        _recibir_hasta(ws, "informe")


def test_sin_memoria_no_guarda(cliente):
    with cliente.websocket_connect("/ws") as ws:
        _enviar(ws, tipo="verificar", afirmacion="Efímera", memoria=False)
        _recibir_hasta(ws, "informe")
    assert cliente.get("/api/historial").json()["historial"] == []
