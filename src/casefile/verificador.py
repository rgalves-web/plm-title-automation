"""Verificação CEGA — família B extrai; o código compara; nada se resolve
em silêncio.

Desenho da ordem integrada (02/09): o verificador recebe pergunta +
evidência + contexto mínimo, e NUNCA a resposta do examinador. A
independência é dupla: outra família de modelo (OpenAI, a mesma do auditor
do minorh) e comparação DETERMINÍSTICA entre o valor extraído e o valor do
claim — normalização de datas/frações/strings é encanamento, não julgamento.
Vereditos possíveis: concordancia, divergencia, evidencia_insuficiente,
nao_verificavel. Divergência fica ABERTA (adjudicação é etapa própria).

Custo: cada chamada B é medida (tokens × tarifa da tabela do loop) e entra
em cost_entries categoria 'verificacao'; teto próprio
CASEFILE_TETO_VERIFICACAO_USD (default 2.0) — ao bater, os claims restantes
ficam SEM verificação declarada, nunca aprovados por omissão.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from src.examinador.loop import RATES

MODELO_B_DEFAULT = "gpt-5.6-terra"


def modelo_b() -> str:
    return os.environ.get("MINORH_AUDITOR_OPENAI", MODELO_B_DEFAULT)


def teto_verificacao() -> float:
    return float(os.environ.get("CASEFILE_TETO_VERIFICACAO_USD", "2.0"))


class _CustoB:
    def __init__(self) -> None:
        self.total = 0.0

    def somar(self, usage: Any) -> float:
        rate = RATES.get(modelo_b(), {"input": 2.0, "output": 12.0})
        entrada = int(getattr(usage, "prompt_tokens", 0) or 0)
        saida = int(getattr(usage, "completion_tokens", 0) or 0)
        custo = round((entrada * rate["input"] + saida * rate["output"])
                      / 1_000_000, 4)
        self.total = round(self.total + custo, 4)
        return custo


def _chamar_b(prompt: str, png: bytes | None = None,
              max_tokens: int = 4000) -> tuple[str, Any]:
    """Uma chamada à família B. Devolve (texto, usage)."""
    from dotenv import load_dotenv
    load_dotenv(".env")
    import openai
    conteudo: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if png is not None:
        import base64
        conteudo.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64,"
                   + base64.standard_b64encode(png).decode("ascii")}})
    resp = openai.OpenAI().chat.completions.create(
        model=modelo_b(), max_completion_tokens=max_tokens,
        messages=[{"role": "user", "content": conteudo}])
    return resp.choices[0].message.content or "", resp.usage


def _json_de(texto: str) -> dict[str, Any] | None:
    try:
        return json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


# --- normalização para comparação determinística ----------------------------

_DATA_RE = re.compile(r"(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})")


def normalizar(valor: Any) -> str:
    texto = str(valor or "").strip().lower()
    m = _DATA_RE.fullmatch(texto)
    if m:
        a, b, c = m.groups()
        if len(a) == 4:                      # yyyy-mm-dd
            return f"{a}-{int(b):02d}-{int(c):02d}"
        if len(c) == 4:                      # mm/dd/yyyy
            return f"{c}-{int(a):02d}-{int(b):02d}"
    texto = re.sub(r"[^a-z0-9/.-]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def comparar(esperado: Any, extraido: Any) -> dict[str, Any]:
    e, x = normalizar(esperado), normalizar(extraido)
    # Valor curto (ex. 'a-811', 'b', '386') casa por TOKEN dentro da frase
    # extraída — 'a-811' concorda com 't.e.l. co. survey a-811'; substring
    # solta não basta ('1' não casa '311').
    iguais = bool(e) and (
        e == x or (len(e) > 6 and (e in x or x in e))
        or e in x.split())
    return {"esperado_norm": e, "extraido_norm": x, "igual": iguais}


# --- o laço de verificação ---------------------------------------------------

def verificar_pergunta(*, repo: Any, claim: dict[str, Any], pergunta: str,
                       campo_do_claim: Any, evidencia_texto: str = "",
                       evidencia_png: bytes | None = None,
                       chamar: Callable[..., tuple[str, Any]] | None = None,
                       custo: _CustoB, session_id: int | None = None
                       ) -> dict[str, Any]:
    """Uma verificação cega. O prompt NÃO contém o valor do examinador."""
    chamar = chamar or _chamar_b
    prompt = (
        "Voce e um verificador independente de due diligence de titulo. "
        "Responda SOMENTE com base na evidencia fornecida — sem conhecimento "
        "externo, sem adivinhar.\n\n"
        f"PERGUNTA: {pergunta}\n\n"
        + (f"EVIDENCIA (texto):\n{evidencia_texto[:6000]}\n\n"
           if evidencia_texto else "EVIDENCIA: a imagem anexa.\n\n")
        + "Responda APENAS um objeto JSON:\n"
          '{"valor": "<sua resposta, ou vazio>",\n'
          ' "trecho": "<trecho literal da evidencia que sustenta>",\n'
          ' "evidencia_suficiente": true|false}')
    texto, usage = chamar(prompt, evidencia_png)
    gasto = custo.somar(usage)
    got = _json_de(texto)
    if got is None:
        veredito, extraido, comp = "nao_verificavel", {}, {
            "motivo": "resposta ilegivel do verificador"}
    elif not got.get("evidencia_suficiente"):
        veredito, extraido, comp = "evidencia_insuficiente", got, {}
    else:
        comp = comparar(campo_do_claim, got.get("valor"))
        veredito = "concordancia" if comp["igual"] else "divergencia"
        extraido = got
    vid = repo.registrar_verificacao(
        claim["id"], pergunta, veredito, modelo_b(), extraido, comp,
        gasto, session_id)
    return {"id": vid, "claim": claim["id"], "verdict": veredito,
            "custo": gasto}


def verificar_lote_exhibit_a(*, repo: Any, unit: dict[str, Any],
                             claims_lease: list[dict[str, Any]],
                             pngs: list[bytes],
                             chamar: Callable[..., tuple[str, Any]] | None
                             = None, custo: _CustoB,
                             session_id: int | None = None
                             ) -> dict[str, int]:
    """Transcrição independente do Exhibit A (2 páginas em pixels) e
    comparação lease a lease — 67 verificações por 2 chamadas."""
    chamar = chamar or _chamar_b
    linhas: list[dict[str, Any]] = []
    for png in pngs:
        prompt = (
            "Transcreva TODAS as linhas da tabela de leases desta pagina "
            "(Exhibit A de uma Declaration of Pooled Unit). Sem resumir, "
            "sem pular linhas. Responda APENAS JSON:\n"
            '{"linhas": [{"lease_no": "...", "lessor": "...", '
            '"vol": "...", "page": "..."}]}')
        try:
            texto, usage = chamar(prompt, png, max_tokens=9000)
        except TypeError:                    # chamador injetado sem o param
            texto, usage = chamar(prompt, png)
        custo.somar(usage)
        got = _json_de(texto)
        if got:
            linhas.extend(got.get("linhas") or [])
    por_lease = {}
    for li in linhas:
        chave = re.sub(r"[\s/]+", "-", str(li.get("lease_no", "")).strip())
        por_lease[chave.upper()] = li
    contagem = {"concordancia": 0, "divergencia": 0,
                "evidencia_insuficiente": 0}
    for c in claims_lease:
        v = c["value"]
        chave = re.sub(r"[\s/]+", "-",
                       str(v.get("lease_no", "")).strip()).upper()
        li = por_lease.get(chave)
        if li is None:
            veredito, comp = "evidencia_insuficiente", {
                "motivo": "linha nao encontrada na transcricao independente"}
        else:
            comps = {campo: comparar(v.get(campo), li.get(campo))
                     for campo in ("lessor", "vol", "page")}
            iguais = all(x["igual"] for x in comps.values())
            veredito = "concordancia" if iguais else "divergencia"
            comp = comps
        contagem[veredito] += 1
        repo.registrar_verificacao(
            c["id"], "transcricao independente do Exhibit A "
                     "(lessor/vol/page por lease_no)", veredito, modelo_b(),
            li or {}, comp, 0.0, session_id)
    return contagem
