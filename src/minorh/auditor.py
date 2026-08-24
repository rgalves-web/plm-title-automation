"""A auditoria de 100% — outra cabeça relê cada célula antes de embarcar.

Todo valor escrito no DDR é conferido, sem amostragem, por um modelo que não
compartilha contexto com o Examinador. O auditor vê só a célula, o valor e a
citação; reabre a página citada (do cache — a página já foi paga) e responde
três perguntas: a página sustenta o valor? contradiz outra célula do arquivo?
é da unidade certa?

A ordem pede o auditor de FAMÍLIA DIFERENTE do Examinador, porque dois modelos
da mesma família erram juntos. Se não houver chave de outro provedor no .env,
cai para Sonnet 5 com contexto isolado — e essa limitação fica REGISTRADA no
relatório, não escondida.

Python aqui só busca a evidência e aplica o veredito do modelo. A regra "nada
embarca reprovado" é regra de embarque do operador, não juízo de title.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.examinador.loop import RATES, Usage

MODELO_RESERVA = "claude-sonnet-5"

PROMPT = """Voce audita UMA celula de um Due Diligence Report antes de ela ir
ao cliente. Voce nao escreveu o valor e nao deve confiar em quem escreveu.

Unidade: {unidade}

Celula: {celula}
Valor escrito: {valor!r}
Citacao dada: {documento}, pagina {pagina}, trecho: {trecho!r}

Conteudo da pagina citada ({modo}):
---
{pagina_conteudo}
---

Valores das demais celulas do arquivo (para checar contradicao):
{listagem}

Distincao que importa: celula ORDINAL/ESTRUTURAL (numero de ordem ou de
sequencia — o "1"/"2" de uma lista, o NO. de uma linha, o L# de um lease na
ordem do arquivo) nao afirma fato de title; o ordinal nasce do ARQUIVO, nao da
pagina. Para essas, "sustenta" = a ordem/contagem e consistente com as demais
celulas listadas e a pagina nao a contradiz — nunca exija que a pagina
"prove" o numero de ordem. O que e ou nao ordinal e julgamento seu.

Responda APENAS um objeto JSON:
{{"sustenta": true|false,        // a pagina citada sustenta o valor escrito?
  "contradiz": null|"<celula>",  // contradiz alguma outra celula listada?
  "unidade_certa": true|false,   // o conteudo e da unidade em questao?
  "motivo": "<UMA frase curta>"}}
"""

# O reforco da segunda tentativa. Repetir o mesmo prompt apos um JSON truncado
# reproduz o truncamento; a segunda chamada pede explicitamente o minimo.
REFORCO = "\n\nATENCAO: responda SOMENTE o objeto JSON, motivo em ate 20 palavras."


@dataclass
class Veredito:
    celula: str
    valor: str
    citacao: str
    aprovada: bool
    sustenta: bool
    contradiz: str | None
    unidade_certa: bool
    motivo: str

    def to_dict(self) -> dict[str, Any]:
        return {"celula": self.celula, "valor": self.valor,
                "citacao": self.citacao, "aprovada": self.aprovada,
                "sustenta": self.sustenta, "contradiz": self.contradiz,
                "unidade_certa": self.unidade_certa, "motivo": self.motivo}


@dataclass
class Auditor:
    provedor: str                   # "openai" | "anthropic"
    modelo: str
    limitacao: str = ""
    uso: Usage = field(default_factory=Usage)
    _client: Any = None

    @classmethod
    def escolher(cls) -> "Auditor":
        """Segundo provedor se houver chave; senão, a reserva declarada."""
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
        except Exception:
            pass
        if os.environ.get("OPENAI_API_KEY"):
            try:
                import openai
                modelo = os.environ.get("MINORH_AUDITOR_OPENAI",
                                        "gpt-4o-mini")
                return cls(provedor="openai", modelo=modelo,
                           _client=openai.OpenAI())
            except ImportError:
                pass
        import anthropic
        return cls(
            provedor="anthropic", modelo=MODELO_RESERVA,
            limitacao=("LIMITACAO REGISTRADA: nenhuma chave de segundo "
                       "provedor no .env — auditoria feita por "
                       f"{MODELO_RESERVA} (mesma familia do Examinador), em "
                       "contexto isolado. Cabecas da mesma familia podem "
                       "errar juntas."),
            _client=anthropic.Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"]))

    def auditar(self, *, unidade: str, celula: str, valor: str,
                documento: str, pagina: Any, trecho: str,
                pagina_conteudo: str, modo: str,
                listagem: str) -> Veredito:
        prompt = PROMPT.format(unidade=unidade, celula=celula, valor=valor,
                               documento=documento, pagina=pagina,
                               trecho=trecho, pagina_conteudo=pagina_conteudo,
                               modo=modo, listagem=listagem)
        citacao = f"{documento} p.{pagina}"
        for tentativa in range(2):      # a repeticao pede o JSON minimo
            texto = self._chamar(prompt + (REFORCO if tentativa else ""))
            veredito = _parse(texto)
            if veredito is not None:
                sustenta = bool(veredito.get("sustenta"))
                contradiz = veredito.get("contradiz") or None
                unidade_ok = bool(veredito.get("unidade_certa"))
                return Veredito(
                    celula=celula, valor=valor, citacao=citacao,
                    aprovada=sustenta and unidade_ok and not contradiz,
                    sustenta=sustenta, contradiz=contradiz,
                    unidade_certa=unidade_ok,
                    motivo=str(veredito.get("motivo") or ""))
        # Sem veredito legivel: NADA embarca sem veredito, entao reprova.
        return Veredito(celula=celula, valor=valor, citacao=citacao,
                        aprovada=False, sustenta=False, contradiz=None,
                        unidade_certa=False,
                        motivo="auditor nao produziu veredito legivel (2x)")

    def _chamar(self, prompt: str) -> str:
        if self.provedor == "openai":
            resp = self._client.chat.completions.create(
                model=self.modelo,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=900)
            usage = resp.usage
            # prompt_tokens INCLUI os cacheados; separar para a tarifa de
            # cache lido não superestimar o custo do ramo B.
            detalhes = getattr(usage, "prompt_tokens_details", None)
            cacheados = int(getattr(detalhes, "cached_tokens", 0) or 0)
            self.uso.input += int(getattr(usage, "prompt_tokens", 0) or 0) \
                - cacheados
            self.uso.cache_read += cacheados
            self.uso.output += int(getattr(usage, "completion_tokens", 0) or 0)
            return resp.choices[0].message.content or ""
        msg = self._client.messages.create(
            model=self.modelo, max_tokens=900,
            messages=[{"role": "user", "content": prompt}])
        self.uso.add(msg.usage)
        return "".join(b.text for b in msg.content
                       if getattr(b, "type", "") == "text")

    def custo(self) -> float | None:
        # Qualquer provedor: a tabela RATES decide. Modelo fora dela devolve
        # None — tokens sempre reportados, custo nunca inventado.
        return self.uso.cost(self.modelo)


_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _parse(texto: str) -> dict[str, Any] | None:
    m = _JSON.search(texto or "")
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
        return got if isinstance(got, dict) else None
    except json.JSONDecodeError:
        return None
