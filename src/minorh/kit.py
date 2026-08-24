"""O kit carbon-copy do ship — a alocação é do modelo, a cópia é da caneta.

Spec: `docs/PLM_PHASE1_SUBMISSION_SPEC.md` + SOP §10 (estrutura controladora
de 21/07, S10). A árvore `1. Landman Submitted/` nasce em
`_minorh/ship/kit/` e `minorh publicar` a congela em `<UNIT>/SUBMISSION PLM/`.

Divisão de trabalho (doc governante §2):

  MODELO   decide em qual pasta cada arquivo do corpus entra, com que nome, e
           o que fica de fora com que motivo (fichas `category-to-ddr-*`,
           `sop-10-formato-e-empacotamento`). O Yes/No da checklist também é
           dele, auditado como qualquer célula.
  CANETA   cria a árvore, copia bytes, confere md5 round-trip, recusa publicar
           por cima de pacote entregue. Plumbing de cópia extraído do padrão de
           `src/knowledge/kit_builder.py` (build_tree: COPIES only, nada é
           movido) — sem nenhum julgamento de conteúdo.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from src.examinador.loop import run_loop
from src.knowledge.write_roots import record_write

RAIZ_KIT = "1. Landman Submitted"

# A árvore da spec. "PLM Report" é abastecida pela caneta (o DDR do ship);
# as demais recebem o que o modelo alocar.
PASTAS = ("Leases", "PLM Report", "Seller's Files", "Title Documents",
          "Title Opinions", "Unit Designation", "Well Files")
PASTAS_ALOCAVEIS = tuple(p for p in PASTAS if p != "PLM Report")

FERRAMENTAS_KIT: list[dict[str, Any]] = [
    {
        "name": "alocar_arquivo",
        "description": (
            "Aloca UM arquivo do corpus a uma pasta do kit de submissao. "
            "`destino` comeca com uma das pastas da spec (Leases, Seller's "
            "Files, Title Documents, Title Opinions, Unit Designation, Well "
            "Files) e pode ter subpasta (ex. 'Title Opinions/Unit Tract 1'). "
            "`novo_nome` segue a convencao da spec (ex. 'L1 - 368.522 - "
            "Fulana OGL.pdf', 'volume.page.pdf'); vazio mantem o nome."),
        "input_schema": {"type": "object", "properties": {
            "documento": {"type": "string",
                          "description": "nome exato no corpus (FILES/)"},
            "destino": {"type": "string"},
            "novo_nome": {"type": "string"},
            "por_que": {"type": "string",
                        "description": "uma frase: por que esta pasta"}},
            "required": ["documento", "destino", "por_que"]},
    },
    {
        "name": "nao_alocar",
        "description": (
            "Declara que um arquivo do corpus fica FORA do kit, com motivo "
            "(ex. duplicata, screenshot, correspondencia interna, fora do "
            "escopo). Arquivo sem decisao aparece no relatorio como "
            "pendencia — decida todos."),
        "input_schema": {"type": "object", "properties": {
            "documento": {"type": "string"},
            "motivo": {"type": "string"}},
            "required": ["documento", "motivo"]},
    },
]

SISTEMA_KIT = """Voce e o landman responsavel pela unidade e vai montar o KIT
DE SUBMISSAO (arvore '1. Landman Submitted/' da spec PLM). O DDR ja esta
pronto e sera colocado em 'PLM Report/' pelo sistema — seu trabalho e decidir
o destino de CADA arquivo do corpus:

1. Para cada arquivo: `alocar_arquivo` (pasta certa + nome conforme a spec)
   ou `nao_alocar` (com motivo). Nenhum arquivo fica sem decisao.
2. Consulte as fichas (`read_knowledge`): `sop-10-formato-e-empacotamento`,
   `category-to-ddr-*` e as `categories-*` dizem o que vai onde e como nomear.
3. Leases: 'L# - book.page - Lessor OGL' (L# = ordem no Lease Review).
   Title Documents: 'volume.page'. Title Opinions: subpasta 'Unit Tract N'.
   Unit Designation: DPU + amendments 'book.page'. Seller's Files: so o
   relevante — sem mass upload. Well Files: suporte RRC dos wells atribuidos.
4. Evite duplicatas: o mesmo TO nao entra duas vezes.

Quando todo arquivo tiver decisao, pare de pedir ferramentas e resuma."""


def _md5(dados: bytes) -> str:
    return hashlib.md5(dados).hexdigest()


class KitCongelado(RuntimeError):
    """`SUBMISSION PLM/` já existe — pacote entregue é intocável."""


class Md5Divergente(AssertionError):
    """A cópia não bate byte a byte com a origem."""


def alocar(*, pasta: Path, corpus: Any, memoria: Any, modelo: str,
           dispatch_leitura: dict[str, Any], client: Any = None,
           max_cost_usd: float = 10.0) -> tuple[dict[str, Any], Any]:
    """Sessão de alocação. Devolve as decisões do modelo e o log do laço."""
    alocados: list[dict[str, str]] = []
    fora: list[dict[str, str]] = []
    nomes = set(corpus.names())

    def _alocar(documento: str, destino: str, por_que: str,
                novo_nome: str = "") -> dict[str, Any]:
        if documento not in nomes:
            raise ValueError(f"{documento!r} nao esta no corpus — "
                             f"use list_documents")
        raiz = destino.replace("\\", "/").split("/", 1)[0]
        if raiz not in PASTAS_ALOCAVEIS:
            raise ValueError(
                f"destino {destino!r} nao comeca com uma pasta da spec: "
                f"{', '.join(PASTAS_ALOCAVEIS)}")
        alocados.append({"documento": documento, "destino": destino,
                         "novo_nome": novo_nome or Path(documento).name,
                         "por_que": por_que})
        return {"alocado": documento, "destino": destino}

    def _nao_alocar(documento: str, motivo: str) -> dict[str, Any]:
        if documento not in nomes:
            raise ValueError(f"{documento!r} nao esta no corpus")
        fora.append({"documento": documento, "motivo": motivo})
        return {"fora_do_kit": documento}

    dispatch = dict(dispatch_leitura)
    dispatch["alocar_arquivo"] = _alocar
    dispatch["nao_alocar"] = _nao_alocar

    from src.minorh.ship import _leitura_schemas
    ferramentas_leitura = [t for t in _leitura_schemas()
                           if t["name"] in dispatch_leitura]

    task = (f"UNIDADE: {pasta.name}\n\nARQUIVOS DO CORPUS "
            f"({len(nomes)}):\n"
            + "\n".join(f"- {n}" for n in sorted(nomes))
            + "\n\nMEMORIA DA UNIDADE (para reconhecer o que cada arquivo "
              "e):\n" + memoria.dump_markdown()
            + "\n\nDecida o destino de cada arquivo.")
    log, _ = run_loop(system=SISTEMA_KIT, task=task,
                      tools=FERRAMENTAS_KIT + ferramentas_leitura,
                      dispatch=dispatch, model=modelo, max_turns=80,
                      max_cost_usd=max_cost_usd, client=client)
    sem_decisao = sorted(nomes - {a["documento"] for a in alocados}
                         - {f["documento"] for f in fora})
    return {"alocados": alocados, "fora_do_kit": fora,
            "sem_decisao": sem_decisao}, log


def montar(*, pasta: Path, corpus: Any, alocacao: dict[str, Any],
           ddr: Path, checklist: Path | None = None) -> dict[str, Any]:
    """A caneta: árvore da spec + cópias com md5 round-trip. Zero decisão."""
    kit_dir = pasta / "_minorh" / "ship" / "kit" / RAIZ_KIT
    if kit_dir.exists():
        shutil.rmtree(kit_dir)
    for nome in PASTAS:
        (kit_dir / nome).mkdir(parents=True, exist_ok=True)

    copiados: list[dict[str, str]] = []

    def _colocar(dados: bytes, destino: Path, origem: str) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino = Path(record_write(destino))
        destino.write_bytes(dados)
        relido = _md5(destino.read_bytes())
        if relido != _md5(dados):
            raise Md5Divergente(f"{destino} nao bate com a origem {origem}")
        copiados.append({"origem": origem,
                         "destino": str(destino.relative_to(kit_dir)),
                         "md5": relido})

    unit_name = pasta.name.title()
    _colocar(ddr.read_bytes(), kit_dir / "PLM Report" /
             f"DDR - {unit_name}.xlsx", str(ddr))
    if checklist is not None:
        _colocar(checklist.read_bytes(), kit_dir / "Phase I - Checklist.xlsx",
                 str(checklist))

    for a in alocacao["alocados"]:
        destino = kit_dir / a["destino"].replace("\\", "/") / a["novo_nome"]
        _colocar(corpus.read_bytes(a["documento"]), destino, a["documento"])

    relatorio = {
        "raiz": str(kit_dir),
        "copiados": copiados,
        "md5_roundtrip": f"{len(copiados)}/{len(copiados)}",
        "fora_do_kit": alocacao["fora_do_kit"],
        "sem_decisao": alocacao["sem_decisao"],
        "checklist": ("no kit" if checklist is not None else
                      "template ausente na unidade — item declarado, nao "
                      "montado"),
    }
    rel = Path(record_write(pasta / "_minorh" / "ship" /
                            "RELATORIO_KIT.json"))
    rel.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    return relatorio


def publicar(pasta: Path) -> dict[str, Any]:
    """Copia `_minorh/ship/kit/` para `<UNIT>/SUBMISSION PLM/`.

    Recusa se o destino já existir — pacote entregue é congelado. Round-trip
    md5 de 100% dos arquivos após a cópia."""
    origem = pasta / "_minorh" / "ship" / "kit"
    if not (origem / RAIZ_KIT).is_dir():
        raise SystemExit(f"nao ha kit montado em {origem} — rode "
                         f"`minorh ship` antes.")
    destino = pasta / "SUBMISSION PLM"
    if destino.exists():
        raise KitCongelado(
            f"{destino} ja existe — pacote entregue e congelado. Nada foi "
            f"escrito. Se a entrega anterior estiver errada, o operador "
            f"decide o que fazer com ela; o sistema nao sobrescreve.")
    shutil.copytree(origem, destino)

    conferidos = 0
    for arquivo in sorted(origem.rglob("*")):
        if not arquivo.is_file():
            continue
        gemeo = destino / arquivo.relative_to(origem)
        if _md5(gemeo.read_bytes()) != _md5(arquivo.read_bytes()):
            raise Md5Divergente(f"round-trip falhou: {gemeo}")
        conferidos += 1
    return {"publicado_em": str(destino),
            "md5_roundtrip": f"{conferidos}/{conferidos}"}
