"""Etapa A da arquitetura agêntica: carregador e validador das fichas.
Plumbing — forma, identidade, referência cruzada. Nunca julgamento."""
import json
import textwrap

import pytest

from src.casefile import agentes, cli

ESQUEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema",
           "type": "object"}

ROLE = """\
    ---
    type: Role
    title: Pesquisador
    description: Busca numa fonte.
    status: draft
    generated:
      by: cowork/claude-opus-5-5
      at: 2026-09-27
    verified: []
    saida_esquema: resultado_pesquisa
    nivel_modelo: medio
    verifica: amostral
    ferramentas: [registrar_pesquisa]
    ---
    ## Regras
    1. Ausência só vale com população.
    """

PACK = """\
    ---
    type: Domain Pack
    title: pacote-sintetico
    description: Pacote de teste.
    status: draft
    generated:
      by: process:teste
      at: 2026-09-27
    verified: [human:renato]
    sources:
      - resource: docs/X.md
        id: x
    ---
    # pacote-sintetico
    """

LESSON = """\
    ---
    type: Lesson
    title: Lição sintética
    description: Uma lição.
    status: draft
    generated:
      by: cowork/claude-opus-5-5
      at: 2026-09-28
    verified: []
    funcao: pesquisador
    escopo: {pacote: pacote-sintetico, fonte: Portal}
    sources:
      - resource: checkpoint
        id: ck
    ---
    Corpo da lição.
    """


def _arvore(tmp_path, *, role=ROLE, pack=PACK, lesson=LESSON,
            index='---\nokf_version: "0.2"\n---\n# agentes\n\n'
                  '- [Pesquisador](/nucleo/pesquisador.md)\n',
            esquemas=("resultado_pesquisa",)):
    raiz = tmp_path / "agentes"
    (raiz / "nucleo").mkdir(parents=True)
    (raiz / "pacotes" / "p" / "licoes").mkdir(parents=True)
    (raiz / "esquemas").mkdir()
    (raiz / "index.md").write_text(index, encoding="utf-8")
    (raiz / "log.md").write_text("# log\n\n- criado\n", encoding="utf-8")
    (raiz / "nucleo" / "pesquisador.md").write_text(
        textwrap.dedent(role), encoding="utf-8")
    (raiz / "pacotes" / "p" / "index.md").write_text(
        textwrap.dedent(pack), encoding="utf-8")
    (raiz / "pacotes" / "p" / "licoes" / "licao.md").write_text(
        textwrap.dedent(lesson), encoding="utf-8")
    for nome in esquemas:
        (raiz / "esquemas" / f"{nome}.json").write_text(
            json.dumps(ESQUEMA), encoding="utf-8")
    return raiz


def _ficha(r, rel):
    return next(f for f in r.fichas if f.rel == rel)


def _codigos(ficha):
    return {a.codigo for a in ficha.erros}


def _sem_linha(texto, prefixo):
    return "\n".join(l for l in textwrap.dedent(texto).splitlines()
                     if not l.startswith(prefixo)) + "\n"


def test_fichas_validas_de_cada_tipo_carregam(tmp_path):
    r = agentes.validar(_arvore(tmp_path))
    assert r.ok, [(f.rel, f.erros) for f in r.fichas]
    assert [f.nome for f in r.por_tipo("Role")] == ["pesquisador"]
    assert [f.nome for f in r.por_tipo("Domain Pack")] == ["pacote-sintetico"]
    assert [f.nome for f in r.por_tipo("Lesson")] == ["licao"]
    assert {f.rel for f in r.fichas if f.reservado} == {"index.md", "log.md"}


@pytest.mark.parametrize("campo,codigo", [
    ("type:", "type_ausente"),
    ("status:", "status_ausente"),
    ("verified:", "verified_ausente"),
    ("title:", "title_ausente"),
    ("description:", "description_ausente"),
    ("saida_esquema:", "saida_esquema_ausente"),
    ("nivel_modelo:", "nivel_modelo_ausente"),
    ("verifica:", "verifica_ausente"),
    ("ferramentas:", "ferramentas_ausente"),
])
def test_role_campo_ausente_gera_erro_nomeado(tmp_path, campo, codigo):
    r = agentes.validar(_arvore(tmp_path, role=_sem_linha(ROLE, campo)))
    assert codigo in _codigos(_ficha(r, "nucleo/pesquisador.md"))
    assert not r.ok


def test_generated_by_e_at_ausentes(tmp_path):
    sem_by = _arvore(tmp_path, role=_sem_linha(ROLE, "  by:"))
    assert "generated_by_ausente" in _codigos(
        _ficha(agentes.validar(sem_by), "nucleo/pesquisador.md"))
    (tmp_path / "b").mkdir()
    sem_at = _arvore(tmp_path / "b", role=_sem_linha(ROLE, "  at:"))
    assert "generated_at_ausente" in _codigos(
        _ficha(agentes.validar(sem_at), "nucleo/pesquisador.md"))
    (tmp_path / "c").mkdir()
    sem_gen = _arvore(tmp_path / "c", role=_sem_linha(
        _sem_linha(_sem_linha(ROLE, "  by:"), "  at:"), "generated:"))
    assert "generated_ausente" in _codigos(
        _ficha(agentes.validar(sem_gen), "nucleo/pesquisador.md"))


@pytest.mark.parametrize("troca,codigo", [
    (("status: draft", "status: publicado"), "status_invalido"),
    (("nivel_modelo: medio", "nivel_modelo: enorme"), "nivel_modelo_invalido"),
    (("ferramentas: [registrar_pesquisa]", "ferramentas: registrar"),
     "ferramentas_nao_lista"),
    (("verified: []", "verified: renato"), "verified_nao_lista"),
    (("by: cowork/claude-opus-5-5", "by: renato"), "ator_invalido"),
    (("verified: []", "verified: [renato]"), "ator_invalido"),
])
def test_role_valor_fora_do_vocabulario(tmp_path, troca, codigo):
    role = textwrap.dedent(ROLE).replace(*troca)
    r = agentes.validar(_arvore(tmp_path, role=role))
    assert codigo in _codigos(_ficha(r, "nucleo/pesquisador.md"))


def test_atores_aceitos(tmp_path):
    role = textwrap.dedent(ROLE).replace(
        "verified: []",
        "verified: [human:renato, process:ci, {by: openai/gpt-5, at: x}]")
    r = agentes.validar(_arvore(tmp_path, role=role))
    assert r.ok, _ficha(r, "nucleo/pesquisador.md").erros


@pytest.mark.parametrize("campo,codigo", [
    ("title:", "title_ausente"),
    ("description:", "description_ausente"),
    ("sources:", "sources_ausente"),
])
def test_pack_campo_ausente(tmp_path, campo, codigo):
    pack = _sem_linha(PACK, campo)
    if campo == "sources:":
        pack = _sem_linha(_sem_linha(pack, "  - resource"), "    id:")
    r = agentes.validar(_arvore(tmp_path, pack=pack))
    assert codigo in _codigos(_ficha(r, "pacotes/p/index.md"))


def test_sources_sem_id_e_recusado(tmp_path):
    pack = _sem_linha(PACK, "    id:")
    r = agentes.validar(_arvore(tmp_path, pack=pack))
    assert "sources_invalido" in _codigos(_ficha(r, "pacotes/p/index.md"))


def test_licao_com_funcao_inexistente_e_recusada(tmp_path):
    lesson = textwrap.dedent(LESSON).replace("funcao: pesquisador",
                                             "funcao: astrologo")
    r = agentes.validar(_arvore(tmp_path, lesson=lesson))
    assert "funcao_inexistente" in _codigos(
        _ficha(r, "pacotes/p/licoes/licao.md"))
    assert not r.ok


def test_licao_com_pacote_inexistente_e_recusada(tmp_path):
    lesson = textwrap.dedent(LESSON).replace("pacote: pacote-sintetico",
                                             "pacote: brasil-fundiario")
    r = agentes.validar(_arvore(tmp_path, lesson=lesson))
    assert "pacote_inexistente" in _codigos(
        _ficha(r, "pacotes/p/licoes/licao.md"))


def test_licao_sem_funcao_escopo_ou_sources(tmp_path):
    lesson = _sem_linha(_sem_linha(LESSON, "funcao:"), "escopo:")
    lesson = _sem_linha(_sem_linha(_sem_linha(lesson, "sources:"),
                                   "  - resource"), "    id:")
    r = agentes.validar(_arvore(tmp_path, lesson=lesson))
    assert {"funcao_ausente", "escopo_ausente", "sources_ausente"} <= \
        _codigos(_ficha(r, "pacotes/p/licoes/licao.md"))


def test_licao_nao_ancora_em_role_ilegivel(tmp_path):
    """Ficha com frontmatter ilegível não conta como Role existente."""
    role_sem_yaml = "---\ntype: Role\n  : [\n---\n"
    r = agentes.validar(_arvore(tmp_path, role=role_sem_yaml))
    assert "yaml_invalido" in _codigos(_ficha(r, "nucleo/pesquisador.md"))
    assert "funcao_inexistente" in _codigos(
        _ficha(r, "pacotes/p/licoes/licao.md"))


def test_saida_esquema_sem_arquivo_e_recusado(tmp_path):
    r = agentes.validar(_arvore(tmp_path, esquemas=()))
    assert "esquema_inexistente" in _codigos(_ficha(r, "nucleo/pesquisador.md"))
    assert not r.ok


def test_esquema_invalido_como_json_schema_e_recusado(tmp_path):
    raiz = _arvore(tmp_path)
    (raiz / "esquemas" / "resultado_pesquisa.json").write_text(
        json.dumps({"type": "objeto"}), encoding="utf-8")
    r = agentes.validar(raiz)
    assert [a.codigo for a in r.erros_esquemas] == ["esquema_invalido"]
    assert not r.ok


def test_index_raiz_com_chave_extra_e_recusado(tmp_path):
    index = '---\nokf_version: "0.2"\ntitle: agentes\n---\n# agentes\n'
    r = agentes.validar(_arvore(tmp_path, index=index))
    assert "index_raiz_chave_proibida" in _codigos(_ficha(r, "index.md"))
    assert not r.ok


def test_index_raiz_sem_okf_version_e_recusado(tmp_path):
    r = agentes.validar(_arvore(tmp_path, index="# agentes\n"))
    assert "okf_version_ausente" in _codigos(_ficha(r, "index.md"))


def test_ficha_sem_frontmatter_e_recusada(tmp_path):
    raiz = _arvore(tmp_path)
    (raiz / "nucleo" / "solta.md").write_text("# sem cabeçalho\n",
                                              encoding="utf-8")
    r = agentes.validar(raiz)
    assert "frontmatter_ausente" in _codigos(_ficha(r, "nucleo/solta.md"))


def test_index_de_subpasta_sem_frontmatter_e_listagem(tmp_path):
    raiz = _arvore(tmp_path)
    (raiz / "nucleo" / "index.md").write_text("# nucleo\n", encoding="utf-8")
    r = agentes.validar(raiz)
    assert _ficha(r, "nucleo/index.md").reservado
    assert r.ok


def test_link_quebrado_e_aviso_nao_erro(tmp_path):
    role = textwrap.dedent(ROLE) + (
        "\nVer [inexistente](../nada.md), [ok](/nucleo/pesquisador.md), "
        "[web](https://example.com) e nota [^1].\n\n[^1]: fonte.\n")
    r = agentes.validar(_arvore(tmp_path, role=role))
    f = _ficha(r, "nucleo/pesquisador.md")
    assert [a.codigo for a in f.avisos] == ["link_quebrado"]
    assert "../nada.md" in f.avisos[0].mensagem
    assert not f.erros and r.ok


def test_link_da_raiz_resolve_a_partir_de_agentes(tmp_path):
    index = '---\nokf_version: "0.2"\n---\n- [x](/nucleo/sumiu.md)\n'
    r = agentes.validar(_arvore(tmp_path, index=index))
    assert [a.codigo for a in _ficha(r, "index.md").avisos] == \
        ["link_quebrado"]
    assert r.ok


def test_versao_muda_com_um_byte_e_e_estavel(tmp_path):
    p = tmp_path / "f.md"
    p.write_bytes(b"conteudo")
    v1 = agentes.versao(p)
    assert v1 == agentes.versao(p)
    assert len(v1) == 64
    p.write_bytes(b"conteudO")
    assert agentes.versao(p) != v1
    p.write_bytes(b"conteudo")
    assert agentes.versao(p) == v1


def test_cli_validar_sai_com_codigo_de_erro(tmp_path, capsys):
    raiz = _arvore(tmp_path, esquemas=())
    with pytest.raises(SystemExit) as exc:
        cli.main(["agentes", "validar", f"--raiz={raiz}"])
    assert exc.value.code == 1
    saida = capsys.readouterr().out
    assert "esquema_inexistente" in saida
    assert "nucleo/pesquisador.md" in saida


def test_cli_validar_e_listar_ok(tmp_path, capsys):
    raiz = _arvore(tmp_path)
    cli.main(["agentes", "validar", f"--raiz={raiz}"])
    assert "0 erros" in capsys.readouterr().out
    cli.main(["agentes", "listar", f"--raiz={raiz}"])
    saida = capsys.readouterr().out
    v = agentes.versao(raiz / "nucleo" / "pesquisador.md")[:16]
    assert "Funções (1)" in saida and v in saida
    assert "pesquisador @ pacote-sintetico" in saida


# --- integração: o agentes/ real do repo ------------------------------------

def test_agentes_do_repo_passam_na_validacao():
    r = agentes.validar()
    erros = [(f.rel, str(a)) for f in r.fichas for a in f.erros] + \
        [str(a) for a in r.erros_esquemas]
    assert r.ok, erros
    assert len(r.por_tipo("Role")) == 10
    assert {f.nome for f in r.por_tipo("Domain Pack")} == \
        {"title-texas-surface", "title-texas-oil-gas-dd"}


def test_todo_saida_esquema_do_repo_tem_arquivo_e_vice_versa():
    r = agentes.validar()
    usados = {f.front["saida_esquema"] for f in r.por_tipo("Role")}
    assert usados == set(agentes.esquemas_disponiveis(agentes.RAIZ_PADRAO))
    assert len(usados) == 10


def test_esquema_claims_segue_validar_claim():
    """O formato de claims é o de validacao.py: um claim que validar_claim
    aceita passa no esquema; sem trecho, é recusado pelos dois."""
    from src.casefile.validacao import ClaimInvalido, validar_claim
    claim = {"tipo": "fact", "entidade": "Tract 1",
             "valor": {"tipo_resultado": "fato_documental"},
             "documento": "sha256:" + "a" * 64, "pagina": "3",
             "trecho": "grants, sells and conveys", "confianca": "alta",
             "materialidade": "alta"}
    tipos = {"fact": {"required_fields": []}}
    validar_claim(claim, tipos, lambda n: [], lambda s: True)
    assert agentes.validar_saida("claims", {"claims": [claim]}) == []
    sem = dict(claim, trecho="")
    with pytest.raises(ClaimInvalido):
        validar_claim(sem, tipos, lambda n: [], lambda s: True)
    assert agentes.validar_saida("claims", {"claims": [sem]})


def test_esquema_adjudicacao_resolve_ref_para_claims():
    base = {"claim_id": 1, "verificacao_id": 2, "desfecho": "corrigido",
            "material_conclusao_titulo": False, "justificativa": "lido",
            "documento": "x.pdf", "pagina": "1", "trecho": "t",
            "novo_claim": {"tipo": "fact"}}
    erros = agentes.validar_saida("adjudicacao", base)
    assert any("novo_claim" in e for e in erros)


def test_esquema_relatorio_qa_nao_aceita_pronto_com_pendencia():
    item = {"checagem": "links", "estado": "pendente", "detalhe": "2 links"}
    rel = {"lifecycle": "partial", "pronto": True, "itens": [item]}
    assert agentes.validar_saida("relatorio_qa", rel)
    rel["pronto"] = False
    assert agentes.validar_saida("relatorio_qa", rel) == []


def test_esquema_verificacao_invalidada_exige_motivo():
    v = {"claim_id": 1, "question": "q", "verdict": "divergencia",
         "verifier_model": "gpt", "verifier_value": {},
         "source_sha256": "a" * 64, "page": "1",
         "prompt_sha256": "b" * 64, "raw_response": "{}",
         "request_id": "", "status": "invalidada"}
    assert agentes.validar_saida("verificacao", v)
    v["invalidation_reason"] = "página errada"
    assert agentes.validar_saida("verificacao", v) == []
