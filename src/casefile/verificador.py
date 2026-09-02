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


class EvidenciaNaoCorresponde(AssertionError):
    """O payload renderizado não corresponde ao documento/página do claim."""


def afirmar_identidade(claim: dict[str, Any], sha_doc_renderizado: str,
                       pagina_renderizada: Any) -> None:
    """Afirmação MECÂNICA pré-chamada (veredito CTO 02/09): o que vai ao
    verificador é a página do documento que o claim cita — nunca outra."""
    if sha_doc_renderizado != claim["source_sha256"]:
        raise EvidenciaNaoCorresponde(
            f"claim {claim['id']}: documento renderizado "
            f"{sha_doc_renderizado[:12]}… != source_sha256 do claim "
            f"{claim['source_sha256'][:12]}…")
    esperada = str(claim.get("page", "")).split("-")[0].split(",")[0].strip()
    if esperada and str(pagina_renderizada) not in (esperada, str(claim.get("page", ""))):
        raise EvidenciaNaoCorresponde(
            f"claim {claim['id']}: pagina renderizada "
            f"{pagina_renderizada!r} != pagina citada {claim['page']!r}")


def _sha(dados: bytes | str) -> str:
    import hashlib
    if isinstance(dados, str):
        dados = dados.encode("utf-8")
    return hashlib.sha256(dados).hexdigest()


def _chamar_b(prompt: str, png: bytes | None = None,
              max_tokens: int = 4000) -> tuple[str, Any, dict[str, Any]]:
    """Uma chamada à família B. Devolve (texto, usage, meta de rastreio)."""
    from dotenv import load_dotenv
    load_dotenv(".env")
    import openai
    conteudo: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if png is not None:
        import base64
        conteudo.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64,"
                   + base64.standard_b64encode(png).decode("ascii")}})
    params = {"model": modelo_b(), "max_completion_tokens": max_tokens}
    resp = openai.OpenAI().chat.completions.create(
        messages=[{"role": "user", "content": conteudo}], **params)
    meta = {"request_id": getattr(resp, "id", "") or "",
            "model_params": params}
    return resp.choices[0].message.content or "", resp.usage, meta


def _chamada(chamar: Callable[..., Any], prompt: str,
             png: bytes | None = None, max_tokens: int = 4000
             ) -> tuple[str, Any, dict[str, Any]]:
    """Compatível com chamadores injetados que devolvem 2-tupla."""
    try:
        got = chamar(prompt, png, max_tokens=max_tokens)
    except TypeError:
        got = chamar(prompt, png)
    if len(got) == 2:
        texto, usage = got
        return texto, usage, {}
    return got


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
                       sha_doc_renderizado: str | None = None,
                       pagina_renderizada: Any = None,
                       chamar: Callable[..., Any] | None = None,
                       custo: _CustoB, session_id: int | None = None
                       ) -> dict[str, Any]:
    """Uma verificação cega. O prompt NÃO contém o valor do examinador.

    Identidade da evidência é AFIRMADA antes da chamada (quando o chamador
    fornece o sha do documento renderizado) e todo o rastreio — payload,
    prompt, resposta bruta, request_id, parâmetros — vai para o registro."""
    chamar = chamar or _chamar_b
    if sha_doc_renderizado is not None:
        afirmar_identidade(claim, sha_doc_renderizado, pagina_renderizada)
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
    texto, usage, meta = _chamada(chamar, prompt, evidencia_png)
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
    payload = evidencia_png if evidencia_png is not None else \
        evidencia_texto[:6000]
    rastreio = {"source_sha256": claim["source_sha256"],
                "page": str(pagina_renderizada
                            if pagina_renderizada is not None
                            else claim.get("page", "")),
                "evidence_payload_sha256": _sha(payload),
                "prompt_sha256": _sha(prompt),
                "raw_response": texto,
                "request_id": meta.get("request_id", ""),
                "model_params": meta.get("model_params", {})}
    vid = repo.registrar_verificacao(
        claim["id"], pergunta, veredito, modelo_b(), extraido, comp,
        gasto, session_id, rastreio=rastreio)
    return {"id": vid, "claim": claim["id"], "verdict": veredito,
            "custo": gasto}


def verificar_lote_exhibit_a(*, repo: Any, unit: dict[str, Any],
                             claims_lease: list[dict[str, Any]],
                             pngs: list[bytes],
                             sha_doc: str | None = None,
                             chamar: Callable[..., Any] | None = None,
                             custo: _CustoB,
                             session_id: int | None = None
                             ) -> dict[str, int]:
    """Transcrição independente do Exhibit A (2 páginas em pixels) e
    comparação lease a lease — 67 verificações por 2 chamadas."""
    chamar = chamar or _chamar_b
    prompt = (
        "Transcreva TODAS as linhas da tabela de leases desta pagina "
        "(Exhibit A de uma Declaration of Pooled Unit). Sem resumir, "
        "sem pular linhas. Responda APENAS JSON:\n"
        '{"linhas": [{"lease_no": "...", "lessor": "...", '
        '"vol": "...", "page": "..."}]}')
    linhas: list[dict[str, Any]] = []
    brutos: list[str] = []
    ids: list[str] = []
    for png in pngs:
        texto, usage, meta = _chamada(chamar, prompt, png, max_tokens=9000)
        custo.somar(usage)
        brutos.append(texto)
        if meta.get("request_id"):
            ids.append(meta["request_id"])
        got = _json_de(texto)
        if got:
            linhas.extend(got.get("linhas") or [])
    rastreio_base = {
        "page": "3-4 (Exhibit A)",
        "evidence_payload_sha256": _sha(b"".join(pngs)),
        "prompt_sha256": _sha(prompt),
        "raw_response": "\n---\n".join(brutos),
        "request_id": ",".join(ids)}
    por_lease = {}
    for li in linhas:
        chave = re.sub(r"[\s/]+", "-", str(li.get("lease_no", "")).strip())
        por_lease[chave.upper()] = li
    contagem = {"concordancia": 0, "divergencia": 0,
                "evidencia_insuficiente": 0, "nao_verificavel": 0}
    for c in claims_lease:
        # Identidade mecânica: o claim tem que citar EXATAMENTE o documento
        # renderizado — senão a verificação nem se aplica.
        if sha_doc is not None and c["source_sha256"] != sha_doc:
            contagem["nao_verificavel"] += 1
            repo.registrar_verificacao(
                c["id"], "transcricao independente do Exhibit A",
                "nao_verificavel", modelo_b(), {},
                {"motivo": "claim cita documento diferente do renderizado"},
                0.0, session_id,
                rastreio=dict(rastreio_base, source_sha256=sha_doc))
            continue
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
            li or {}, comp, 0.0, session_id,
            rastreio=dict(rastreio_base,
                          source_sha256=c["source_sha256"]))
    return contagem
