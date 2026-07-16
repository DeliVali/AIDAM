"""Sandbox tests: the bwrap argv must be pure and auditable without bwrap;
when bubblewrap IS installed, the confinement gets verified for real
(write isolation, network isolation, timeout kill)."""

import sys
from pathlib import Path

import pytest

from aidam.agente import sandbox
from aidam.agente.sandbox import (
    construir_comando_bwrap,
    ejecutar_confinado,
    hay_bwrap,
)

necesita_bwrap = pytest.mark.skipif(
    not hay_bwrap(), reason="bubblewrap no está instalado"
)


def _contiene_secuencia(argv: list[str], secuencia: list[str]) -> bool:
    n = len(secuencia)
    return any(argv[i:i + n] == secuencia for i in range(len(argv) - n + 1))


# ───────── construir_comando_bwrap (puro, sin bwrap) ─────────


def test_flags_presentes_y_en_orden(tmp_path):
    argv = construir_comando_bwrap(["echo", "hola"], tmp_path)
    assert argv[0] == "bwrap"
    for flag in ("--die-with-parent", "--new-session", "--unshare-user",
                 "--unshare-pid", "--unshare-ipc", "--unshare-uts"):
        assert flag in argv
    # namespaces first, then mounts, then env/chdir, then the command
    assert argv.index("--unshare-user") < argv.index("--ro-bind")
    assert argv.index("--ro-bind") < argv.index("--setenv")
    assert _contiene_secuencia(argv, ["--ro-bind", "/", "/"])
    assert _contiene_secuencia(argv, ["--dev", "/dev"])
    assert _contiene_secuencia(argv, ["--proc", "/proc"])
    assert _contiene_secuencia(argv, ["--tmpfs", "/tmp"])
    assert _contiene_secuencia(argv, ["--bind", str(tmp_path), str(tmp_path)])
    # the command goes verbatim after the -- separator, at the very end
    assert argv[argv.index("--") + 1:] == ["echo", "hola"]


def test_unshare_net_solo_sin_red(tmp_path):
    assert "--unshare-net" in construir_comando_bwrap(["true"], tmp_path)
    assert "--unshare-net" in construir_comando_bwrap(["true"], tmp_path, red=False)
    assert "--unshare-net" not in construir_comando_bwrap(["true"], tmp_path, red=True)


def test_git_se_monta_ro_solo_si_existe(tmp_path):
    git = tmp_path / ".git"
    sin_git = construir_comando_bwrap(["true"], tmp_path)
    assert not _contiene_secuencia(sin_git, ["--ro-bind", str(git), str(git)])
    git.mkdir()
    con_git = construir_comando_bwrap(["true"], tmp_path)
    assert _contiene_secuencia(con_git, ["--ro-bind", str(git), str(git)])


def test_home_y_chdir_apuntan_a_la_raiz(tmp_path):
    argv = construir_comando_bwrap(["true"], tmp_path)
    assert _contiene_secuencia(argv, ["--setenv", "HOME", str(tmp_path)])
    assert _contiene_secuencia(argv, ["--chdir", str(tmp_path)])


def test_ro_extra_se_monta(tmp_path):
    extra = tmp_path / "datos"
    argv = construir_comando_bwrap(["true"], tmp_path, ro_extra=[extra])
    assert _contiene_secuencia(argv, ["--ro-bind", str(extra), str(extra)])


# ───────── ejecutar_confinado ─────────


def test_sin_bwrap_lanza_error_en_espanol(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "hay_bwrap", lambda: False)
    with pytest.raises(RuntimeError, match="bubblewrap no está instalado"):
        sandbox.ejecutar_confinado("echo hola", tmp_path)


@necesita_bwrap
def test_echo_dentro_del_sandbox(tmp_path):
    resultado = ejecutar_confinado(["echo", "hola"], tmp_path)
    assert resultado.codigo == 0
    assert resultado.stdout.strip() == "hola"
    assert resultado.agotado is False


@necesita_bwrap
def test_escribir_en_la_raiz_funciona(tmp_path):
    # str command → bash -lc, and the write survives on the host side
    resultado = ejecutar_confinado("echo contenido > archivo.txt", tmp_path)
    assert resultado.codigo == 0
    assert (tmp_path / "archivo.txt").read_text().strip() == "contenido"


@necesita_bwrap
def test_escribir_fuera_de_la_raiz_falla(tmp_path):
    # unprivileged user inside --unshare-user + / read-only: must fail
    resultado = ejecutar_confinado("touch /usr/aidam_prueba_sandbox", tmp_path)
    assert resultado.codigo != 0
    assert not Path("/usr/aidam_prueba_sandbox").exists()


@necesita_bwrap
def test_sin_red_no_hay_conexion(tmp_path):
    # direct IP (no DNS involved): with --unshare-net the connect fails
    # immediately — nothing ever touches the real network
    codigo = "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)"
    resultado = ejecutar_confinado([sys.executable, "-c", codigo], tmp_path)
    assert resultado.codigo != 0


@necesita_bwrap
def test_con_red_no_se_aisla_el_loopback(tmp_path):
    # sanity check of the flag path: red=True omits --unshare-net, so the
    # sandbox still resolves interfaces; we only assert the command runs
    resultado = ejecutar_confinado(["true"], tmp_path, red=True)
    assert resultado.codigo == 0


@necesita_bwrap
def test_timeout_mata_el_proceso(tmp_path):
    resultado = ejecutar_confinado(["sleep", "5"], tmp_path, timeout=0.5)
    assert resultado.agotado is True
    assert resultado.codigo == 124


@necesita_bwrap
def test_salida_larga_se_trunca(tmp_path):
    resultado = ejecutar_confinado([sys.executable, "-c", "print('x' * 60_000)"], tmp_path)
    assert resultado.codigo == 0
    assert resultado.stdout.endswith("… [truncado]")
    assert len(resultado.stdout) == 50_000 + len("… [truncado]")
