"""Validação estrutural de claims — forma e identidade, nunca conteúdo."""
from __future__ import annotations

import pytest

from src.casefile.validacao import ClaimInvalido, validar_claim
from tests.helpers_casefile import RepoFake

SHA_A = "a" * 64
SHA_B = "b" * 64


def _tipos():
    return RepoFake().tipos_de_claim()


def _resolver(nome):
    return {"files/dpu.pdf": [SHA_A],
            "files/xref.xlsx": [SHA_A, SHA_B]}.get(nome.lower(), [])


def _sha_existe(sha):
    return sha in (SHA_A, SHA_B)


def _claim(**kw):
    base = {"tipo": "lease_in_unit", "entidade": "lease 0001",
            "valor": {"lease_no": "0001", "lessor": "Fulano"},
            "documento": "files/dpu.pdf", "pagina": "3",
            "trecho": "Lease No. 0001, Fulano de Tal, Lessor",
            "confianca": "alta"}
    base.update(kw)
    return base


def test_claim_valido_normaliza_e_resolve_sha():
    got = validar_claim(_claim(), _tipos(), _resolver, _sha_existe)
    assert got["source_sha256"] == SHA_A
    assert got["materiality"] == "media"        # default declarado
    assert got["claim_type"] == "lease_in_unit"


def test_erros_nomeados_de_forma():
    with pytest.raises(ClaimInvalido, match="tipo desconhecido"):
        validar_claim(_claim(tipo="chute"), _tipos(), _resolver, _sha_existe)
    with pytest.raises(ClaimInvalido, match="faltam"):
        validar_claim(_claim(valor={"lease_no": "0001"}), _tipos(),
                      _resolver, _sha_existe)
    with pytest.raises(ClaimInvalido, match="trecho"):
        validar_claim(_claim(trecho="  "), _tipos(), _resolver, _sha_existe)
    with pytest.raises(ClaimInvalido, match="confianca"):
        validar_claim(_claim(confianca="enorme"), _tipos(), _resolver,
                      _sha_existe)


def test_documento_ausente_ambiguo_e_sha_direto():
    with pytest.raises(ClaimInvalido, match="nao esta no censo"):
        validar_claim(_claim(documento="files/nada.pdf"), _tipos(),
                      _resolver, _sha_existe)
    # nome com 2 conteúdos distintos: erro lista os hashes e pede sha256:
    with pytest.raises(ClaimInvalido, match="ambiguo"):
        validar_claim(_claim(documento="files/xref.xlsx"), _tipos(),
                      _resolver, _sha_existe)
    got = validar_claim(_claim(documento=f"sha256:{SHA_B}"), _tipos(),
                        _resolver, _sha_existe)
    assert got["source_sha256"] == SHA_B
    with pytest.raises(ClaimInvalido, match="nao esta no censo"):
        validar_claim(_claim(documento=f"sha256:{'c' * 64}"), _tipos(),
                      _resolver, _sha_existe)
