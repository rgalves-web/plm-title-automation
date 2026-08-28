"""Etapa H (coleta + padrão de submissão) — testes do encanamento.

Pull list com forma completa, ledger de coleta com teto próprio, corte de PNG
pelas alturas reais, validação de carimbo como veredito do modelo (ilegível
nunca aprova), `coletar` que pula o que está no disco e confere o primeiro
documento, gate do ESCOPO.md no ship, e pastas vazias declaradas no kit.
Nenhuma asserção conclui title.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.examinador.cache import PageCache
from src.examinador.corpus import Corpus
from src.minorh.estado import Estado


def _corpus(tmp_path: Path, nomes: dict[str, bytes]) -> Corpus:
    files = tmp_path / "FILES"
    files.mkdir(exist_ok=True)
    for nome, dados in nomes.items():
        (files / nome).write_bytes(dados)
    return Corpus(files, cache=PageCache(tmp_path / "cache"))


@dataclass
class _Uso:
    input_tokens: int = 10
    output_tokens: int = 5
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _Msg:
    content: list[Any]
    usage: _Uso = field(default_factory=_Uso)


@dataclass
class _Use:
    name: str
    input: dict[str, Any]
    id: str = "u1"
    type: str = "tool_use"


@dataclass
class _Texto:
    text: str
    type: str = "text"


class _ClientRoteirizado:
    def __init__(self, roteiro: list[list[Any]]) -> None:
        self.roteiro = roteiro
        self.messages = self

    def create(self, **kw: Any) -> _Msg:
        return _Msg(content=self.roteiro.pop(0))


def _pull_item(**kw: str) -> dict[str, str]:
    base = {"book": "1822", "page": "310", "data": "2012-03-01",
            "instrumento": "Assignment", "grantor": "Fulano",
            "arquivo_alvo": "1822.310.pdf", "condado": "Cooke"}
    base.update(kw)
    return base


# --- H2.1: pull list ---------------------------------------------------------

def test_pull_list_exige_forma_completa_e_round_trip(tmp_path: Path):
    from src.minorh.coleta import (caminho_pull_list, completude,
                                   escrever_pull_list, ler_pull_list)
    with pytest.raises(ValueError, match="sem"):
        escrever_pull_list(tmp_path, [_pull_item(book="")])
    escrever_pull_list(tmp_path, [_pull_item(),
                                  _pull_item(book="2625", page="179",
                                             arquivo_alvo="2625.179.pdf")])
    assert caminho_pull_list(tmp_path).exists()
    itens = ler_pull_list(tmp_path)
    assert len(itens) == 2 and itens[0]["book"] == "1822"
    destino = tmp_path / "FILES"
    destino.mkdir()
    (destino / "1822.310.pdf").write_bytes(b"x")
    got = completude(tmp_path, destino)
    assert got["no_disco"] == 1 and got["faltam"] == ["2625.179.pdf"]


# --- H2.2: ledger de coleta --------------------------------------------------

def test_ledger_de_coleta_soma_e_o_teto_para(tmp_path: Path, monkeypatch):
    from src.minorh.coleta import LedgerColeta
    monkeypatch.setenv("MINORH_TETO_COLETA_USD", "1")
    led = LedgerColeta(tmp_path)
    led.registrar("1822.310.pdf", "capturado")
    led.conferir_teto()                          # $0.50 < $1
    led.registrar("2625.179.pdf", "capturado")
    with pytest.raises(SystemExit, match="TETO DE COLETA"):
        led.conferir_teto()                      # $1.00 >= $1
    relido = LedgerColeta(tmp_path)              # persiste
    assert relido.custo() == 1.0


# --- H2.3: corte pelas alturas ----------------------------------------------

def test_png_para_pdf_corta_pelas_alturas_reais(tmp_path: Path):
    import fitz
    from PIL import Image

    from src.minorh.coleta import png_para_pdf
    img = Image.new("RGB", (100, 300), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with pytest.raises(ValueError, match="alturas soma"):
        png_para_pdf(buf.getvalue(), [100, 100], tmp_path / "x.pdf")
    out = png_para_pdf(buf.getvalue(), [120, 180], tmp_path / "1822.310.pdf")
    with fitz.open(out) as doc:
        assert doc.page_count == 2               # alturas mistas respeitadas


def test_nomes_candidatos_tenta_as_duas_formas():
    from src.minorh.coleta import nomes_candidatos
    assert nomes_candidatos("1822", "310") == ["1822_0310.tif",
                                               "1822_310.tif"]


def test_carimbo_e_veredito_do_modelo_e_ilegivel_nao_valida(tmp_path: Path):
    import fitz

    from src.minorh.coleta import validar_carimbo
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    pdf = tmp_path / "1822.310.pdf"
    doc.save(pdf)
    doc.close()
    aprova = json.dumps({"carimbo_no_topo": True,
                         "book_page_do_carimbo": "1822/310",
                         "corresponde_ao_arquivo": True, "motivo": "ok"})
    ok = validar_carimbo(pdf, book="1822", page="310",
                         chamar=lambda p, png: aprova)
    assert ok["valido"] and ok["paginas_amostradas"] == 3   # 1a, meio, ultima
    ruim = validar_carimbo(pdf, book="1822", page="310",
                           chamar=lambda p, png: "nao sei")
    assert ruim["valido"] is False               # ilegível nunca aprova


# --- H2: o comando coletar ---------------------------------------------------

def test_coletar_pula_disco_confere_o_primeiro_e_lanca_aberturas(
        tmp_path: Path, monkeypatch, capsys):
    from PIL import Image

    from src.minorh.coleta import coletar, escrever_pull_list
    monkeypatch.setenv("MINORH_TETO_COLETA_USD", "25")
    escrever_pull_list(tmp_path, [
        _pull_item(),                                        # já no disco
        _pull_item(book="2625", page="179", arquivo_alvo="2625.179.pdf"),
        _pull_item(book="1834", page="659", arquivo_alvo="1834.659.pdf")])
    files = tmp_path / "FILES"
    files.mkdir()
    (files / "1822.310.pdf").write_bytes(b"ja estava")

    def _cap(item, cdp_url):
        if item["book"] == "1834":
            raise RuntimeError("sem imagem no CD")
        img = Image.new("RGB", (100, 200), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), [200]

    rel = coletar(tmp_path, capturador=_cap,
                  validador=lambda pdf, book, page: {
                      "arquivo": pdf.name, "paginas_amostradas": 1,
                      "valido": True, "vereditos": []})
    assert rel["ja_no_disco"] == 1               # nunca se reabre
    assert rel["coletados"] == ["2625.179.pdf"]
    assert len(rel["falhas"]) == 1               # 1834.659 vira PEDIDOS
    assert rel["aberturas"] == 2                 # a captura e a falha (abertas)
    assert rel["custo_coleta_usd"] == 1.0
    assert rel["completude"]["no_disco"] == 2
    assert "primeiro documento conferido" in capsys.readouterr().out
    assert (tmp_path / "_minorh" / "RELATORIO_COLETA.json").exists()


# --- H1: gate do ESCOPO no ship ---------------------------------------------

def test_escopo_gate_do_ship(tmp_path: Path):
    from src.minorh import cli
    estado = Estado(tmp_path)
    estado.declarar_censo(1, "x")
    (tmp_path / "template.xlsx").write_bytes(
        Path("tests/fixtures/unidade_sintetica/template.xlsx").read_bytes())
    estado.declarar_escopo()                     # declarado, não aceito
    with pytest.raises(SystemExit, match="AINDA N"):
        cli.cmd_ship(tmp_path)
    with pytest.raises(SystemExit, match="ESCOPO"):
        Estado(tmp_path / "outra").aceitar_escopo()
    estado.aceitar_escopo()
    assert Estado(tmp_path).escopo["aceito"]     # persiste


def test_ferramentas_h_escrevem_escopo_pull_list_e_missing(tmp_path: Path):
    from src.examinador.okf import KnowledgeBase
    from src.minorh.ferramentas import montar_dispatch
    from src.minorh.memoria import Memoria
    corpus = _corpus(tmp_path, {"d.csv": b"x"})
    estado = Estado(tmp_path)
    d = montar_dispatch(corpus, KnowledgeBase(tmp_path / "u"),
                        KnowledgeBase(tmp_path / "g"),
                        Memoria(tmp_path / "_minorh" / "memoria.json"),
                        estado)
    got = d["declarar_escopo"](
        escopo_markdown="# ESCOPO\n\nRunsheet pos-certificacao.")
    assert "aceitar" in got["nota"]
    assert (tmp_path / "ESCOPO.md").read_text(
        encoding="utf-8").startswith("# ESCOPO")
    assert Estado(tmp_path).escopo["declarado"]
    got = d["emitir_pull_list"](itens=[_pull_item()])
    assert got["itens"] == 1
    got = d["emitir_missing_files"](linhas=[
        {"lease": "0221795-048", "rotulo": "Full Lease (Have Memo Only)"}])
    assert got["linhas"] == 1
    assert "append-only" in got["nota"]


# --- H3: pastas vazias declaradas no kit ------------------------------------

def test_kit_cria_pastas_declaradas_vazias(tmp_path: Path):
    from src.minorh.kit import RAIZ_KIT, alocar, montar
    from src.minorh.memoria import Memoria
    corpus = _corpus(tmp_path, {"to.pdf": b"opiniao"})
    memoria = Memoria(tmp_path / "_minorh" / "memoria.json")
    client = _ClientRoteirizado([
        [_Use("alocar_arquivo", {"documento": "to.pdf",
                                 "destino": "Title Opinions/Unit Tract 1",
                                 "por_que": "cobre o tract 1"})],
        [_Use("declarar_pasta", {"destino": "Title Opinions/Unit Tract 2",
                                 "por_que": "nenhuma opiniao cobre — vazio "
                                            "declarado vence inexistente"})],
        [_Texto("fim")],
    ])
    alocacao, _ = alocar(pasta=tmp_path, corpus=corpus, memoria=memoria,
                         modelo="claude-opus-5", dispatch_leitura={},
                         client=client)
    ddr = tmp_path / "DDR.xlsx"
    ddr.write_bytes(b"ddr")
    got = montar(pasta=tmp_path, corpus=corpus, alocacao=alocacao, ddr=ddr)
    kit = tmp_path / "_minorh" / "ship" / "kit" / RAIZ_KIT
    assert (kit / "Title Opinions" / "Unit Tract 1" / "to.pdf").exists()
    assert (kit / "Title Opinions" / "Unit Tract 2").is_dir()   # vazia, existe
    assert got["pastas_declaradas"][0]["destino"] == \
        "Title Opinions/Unit Tract 2"
