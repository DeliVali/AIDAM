"""Knob plumbing of the isolated LLM worker (resource program).

`_config_llama` is pure env→kwargs: testable without llama.cpp or a model.
An empty environment must reproduce the historical defaults exactly.
"""

import aidam.llm_worker as worker

_PERILLAS = (
    "AIDAM_MIMO_N_CTX", "AIDAM_MIMO_GPU_LAYERS", "AIDAM_MIMO_FLASH_ATTN",
    "AIDAM_MIMO_KV_TIPO", "AIDAM_MIMO_HILOS", "AIDAM_MIMO_LOTE",
    "AIDAM_MIMO_SIN_MMAP", "AIDAM_MIMO_MLOCK", "AIDAM_MIMO_BORRADOR",
)


def _limpiar(monkeypatch):
    for var in _PERILLAS:
        monkeypatch.delenv(var, raising=False)


def test_entorno_vacio_reproduce_los_defaults_historicos(monkeypatch):
    _limpiar(monkeypatch)
    assert worker._config_llama() == {
        "n_ctx": 6144, "n_gpu_layers": -1, "verbose": False,
    }


def test_perillas_se_traducen_a_kwargs(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("AIDAM_MIMO_N_CTX", "4096")
    monkeypatch.setenv("AIDAM_MIMO_GPU_LAYERS", "20")
    monkeypatch.setenv("AIDAM_MIMO_FLASH_ATTN", "1")
    monkeypatch.setenv("AIDAM_MIMO_HILOS", "6")
    monkeypatch.setenv("AIDAM_MIMO_LOTE", "256")
    monkeypatch.setenv("AIDAM_MIMO_SIN_MMAP", "1")
    monkeypatch.setenv("AIDAM_MIMO_MLOCK", "1")
    config = worker._config_llama()
    assert config["n_ctx"] == 4096 and config["n_gpu_layers"] == 20
    assert config["flash_attn"] is True and config["n_threads"] == 6
    assert config["n_batch"] == 256
    assert config["use_mmap"] is False and config["use_mlock"] is True


def test_kv_cuantizado_fuerza_flash_attention(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("AIDAM_MIMO_KV_TIPO", "q8_0")
    config = worker._config_llama()
    assert config["type_k"] == 8 and config["type_v"] == 8
    assert config["flash_attn"] is True  # quantized V-cache requires it


def test_kv_desconocido_se_ignora(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("AIDAM_MIMO_KV_TIPO", "f32")
    config = worker._config_llama()
    assert "type_k" not in config and "flash_attn" not in config


def test_borrador_solo_con_lookup(monkeypatch):
    _limpiar(monkeypatch)
    assert worker._borrador() is None
    monkeypatch.setenv("AIDAM_MIMO_BORRADOR", "otracosa")
    assert worker._borrador() is None
