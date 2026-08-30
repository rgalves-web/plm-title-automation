"""Validação ESTRUTURAL de claims — forma, identificadores, existência.

O que se confere aqui: o tipo existe e está ativo, os campos exigidos pelo
tipo estão presentes em `valor`, o documento resolve para um sha256 do censo
(nome ambíguo entre dois conteúdos = erro nomeado com os dois hashes), o
trecho não é vazio, os enums valem. O que NUNCA se confere aqui: se o valor
está certo, se o trecho sustenta o valor, se o documento é o que o modelo diz
— isso é julgamento, e julgamento é de outra cabeça de IA (VS3+).

Reprovado volta ao modelo como erro nomeado, item a item — o modelo redecide;
nunca vira aceitação parcial silenciosa.
"""
from __future__ import annotations

import re
from typing import Any, Callable

_SHA_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_ENUM = ("alta", "media", "baixa")


class ClaimInvalido(ValueError):
    """A afirmação não tem a forma, o identificador ou a evidência exigidos."""


def validar_claim(item: dict[str, Any], tipos: dict[str, dict[str, Any]],
                  resolver_nome: Callable[[str], list[str]],
                  sha_existe: Callable[[str], bool]) -> dict[str, Any]:
    """Devolve o claim normalizado (com source_sha256) ou levanta ClaimInvalido."""
    tipo = str(item.get("tipo") or "").strip()
    if tipo not in tipos:
        raise ClaimInvalido(
            f"tipo desconhecido ou inativo: {tipo!r}. Ativos: "
            f"{sorted(tipos)}")

    valor = item.get("valor")
    if not isinstance(valor, dict):
        raise ClaimInvalido(f"`valor` deve ser objeto; veio "
                            f"{type(valor).__name__}")
    exigidos = list(tipos[tipo].get("required_fields") or [])
    faltam = [c for c in exigidos if c not in valor]
    if faltam:
        raise ClaimInvalido(
            f"tipo {tipo!r} exige as chaves {exigidos} em `valor`; "
            f"faltam: {faltam}")

    entidade = str(item.get("entidade") or "").strip()
    if not entidade:
        raise ClaimInvalido("`entidade` vazia")

    trecho = str(item.get("trecho") or "").strip()
    if not trecho:
        raise ClaimInvalido(
            "`trecho` vazio — evidencia e citacao literal, nunca ausencia")

    pagina = str(item.get("pagina") or "").strip()
    if not pagina:
        raise ClaimInvalido("`pagina` vazia")

    confianca = str(item.get("confianca") or "").strip()
    if confianca not in _ENUM:
        raise ClaimInvalido(f"`confianca` deve ser uma de {_ENUM}; "
                            f"veio {confianca!r}")
    materialidade = str(item.get("materialidade") or "media").strip()
    if materialidade not in _ENUM:
        raise ClaimInvalido(f"`materialidade` deve ser uma de {_ENUM}; "
                            f"veio {materialidade!r}")

    documento = str(item.get("documento") or "").strip()
    sha = _resolver(documento, resolver_nome, sha_existe)

    return {"claim_type": tipo, "entity": entidade, "value": valor,
            "source_sha256": sha, "page": pagina, "evidence": trecho,
            "confidence": confianca, "materiality": materialidade}


def _resolver(documento: str, resolver_nome: Callable[[str], list[str]],
              sha_existe: Callable[[str], bool]) -> str:
    if not documento:
        raise ClaimInvalido("`documento` vazio — toda afirmacao aponta para "
                            "um conteudo do censo")
    m = _SHA_RE.match(documento.lower())
    if m:
        sha = m.group(1)
        if not sha_existe(sha):
            raise ClaimInvalido(
                f"sha256 {sha[:12]}… nao esta no censo desta unit")
        return sha
    hashes = resolver_nome(documento)
    if not hashes:
        raise ClaimInvalido(
            f"documento {documento!r} nao esta no censo — use o nome logico "
            f"exato de `list_documents` ou sha256:<hash>")
    if len(hashes) > 1:
        raise ClaimInvalido(
            f"documento {documento!r} e ambiguo: {len(hashes)} conteudos "
            f"distintos com esse nome ({', '.join(h[:12] + '…' for h in hashes)})"
            f" — cite sha256:<hash completo> para desambiguar")
    return hashes[0]
