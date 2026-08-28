"""`minorh coletar` — a camada de coleta (Etapa H2, receita provada na Webb B).

Divisão de trabalho, como sempre (doc governante §2):

  MODELO   decide O QUE buscar: a pull list nasce citada (`emitir_pull_list`),
           um item por instrumento do runsheet; e julga a VALIDADE de cada
           captura (carimbo Doc/Bk/Vol/Pg no topo, book.page do carimbo ==
           nome do arquivo) — amostrada pela família B com a página em pixels.
  CANETA   executa: navega o Historical File Viewer pela receita da ficha
           `coleta-courthousedirect-receita-provada`, captura canvases,
           corta o PNG pelas ALTURAS REAIS de cada canvas (nunca divisão
           uniforme), grava `book.page.pdf`, lança US$ 0,50 por abertura no
           ledger de coleta da unit e NUNCA reabre documento já no disco.

Proibições absolutas (ordem H): a automação nunca insere pagamento nem
credencial; o operador loga o Chrome corporativo e concede a permissão de
downloads automáticos (pré-requisitos que viram PEDIDOS.md quando faltam).
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

CUSTO_ABERTURA_USD = 0.50
TETO_COLETA_DEFAULT = 25.0
# ≥ ~1150 px de largura de canvas ≈ 130 DPI — abaixo disso o carimbo borra.
LARGURA_ALVO_PX = 1150

COLUNAS_PULL = ("book", "page", "data", "instrumento", "grantor",
                "arquivo_alvo", "condado")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def teto_coleta() -> float:
    return float(os.environ.get("MINORH_TETO_COLETA_USD",
                                str(TETO_COLETA_DEFAULT)))


# --------------------------------------------------------------- pull list
def caminho_pull_list(pasta: Path) -> Path:
    return Path(pasta) / f"PULL LIST - {Path(pasta).name}.csv"


def escrever_pull_list(pasta: Path, itens: list[dict[str, str]]) -> Path:
    """Grava o CSV da pull list (H2.1). Forma, não julgamento: cada item já
    vem decidido e citado pelo modelo; aqui só se exige a forma completa."""
    for i, item in enumerate(itens):
        faltam = [c for c in COLUNAS_PULL if not str(item.get(c, "")).strip()]
        if faltam:
            raise ValueError(f"item {i + 1} da pull list sem {faltam} — "
                             f"todo item carrega book, page, data, "
                             f"instrumento, grantor, arquivo_alvo e condado")
    path = caminho_pull_list(pasta)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS_PULL)
        w.writeheader()
        for item in itens:
            w.writerow({c: str(item[c]).strip() for c in COLUNAS_PULL})
    return path


def ler_pull_list(pasta: Path) -> list[dict[str, str]]:
    path = caminho_pull_list(pasta)
    if not path.exists():
        raise SystemExit(f"não há pull list em {path} — o Examinador a emite "
                         f"com `emitir_pull_list` ao fechar o rascunho do "
                         f"runsheet.")
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def completude(pasta: Path, destino: Path) -> dict[str, Any]:
    """A régua: quantos `arquivo_alvo` da pull list existem em `destino`.
    Contagem pura — é a mesma lista que mede `Title Documents/` no fim."""
    itens = ler_pull_list(pasta)
    tem, falta = [], []
    for item in itens:
        (tem if (Path(destino) / item["arquivo_alvo"]).exists()
         else falta).append(item["arquivo_alvo"])
    return {"total": len(itens), "no_disco": len(tem), "faltam": falta}


# ------------------------------------------------------- ledger de coleta
class LedgerColeta:
    """Aberturas pagas (US$ 0,50 cada) contra o teto de coleta da unit —
    contabilidade separada do teto de modelo. Documento no disco nunca se
    reabre; ao bater o teto, para e reporta, nunca estoura."""

    def __init__(self, pasta: Path) -> None:
        self.path = Path(pasta) / "_minorh" / "coleta.json"
        self.aberturas: list[dict[str, Any]] = []
        if self.path.exists():
            self.aberturas = json.loads(
                self.path.read_text(encoding="utf-8"))["aberturas"]

    def custo(self) -> float:
        return round(sum(a["custo_usd"] for a in self.aberturas), 2)

    def registrar(self, arquivo: str, resultado: str) -> None:
        self.aberturas.append({"arquivo": arquivo, "quando": _now(),
                               "custo_usd": CUSTO_ABERTURA_USD,
                               "resultado": resultado})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"custo_total_usd": self.custo(), "aberturas": self.aberturas},
            indent=1, ensure_ascii=False), encoding="utf-8")

    def conferir_teto(self) -> None:
        if self.custo() >= teto_coleta():
            raise SystemExit(
                f"TETO DE COLETA ATINGIDO: ${self.custo()} em "
                f"{len(self.aberturas)} abertura(s) ≥ ${teto_coleta()} "
                f"(MINORH_TETO_COLETA_USD). Nada mais foi aberto. Para "
                f"autorizar exceção: MINORH_TETO_COLETA_USD=<novo> "
                f"minorh coletar")


# ------------------------------------------------- PNG -> PDF multipágina
def png_para_pdf(png: bytes, alturas: list[int], destino: Path) -> Path:
    """Corta o PNG composto pelas ALTURAS individuais dos canvases — as
    fronteiras exatas de página. Nunca divisão uniforme: há instrumentos com
    páginas carta e ofício misturadas (4 documentos da Webb B saíram cortados
    no meio por isso)."""
    from PIL import Image

    img = Image.open(io.BytesIO(png))
    if sum(alturas) != img.height:
        raise ValueError(
            f"vetor de alturas soma {sum(alturas)}px mas o PNG tem "
            f"{img.height}px — as alturas vêm dos canvases reais, não de "
            f"divisão; recapturar em vez de adivinhar o corte")
    paginas = []
    y = 0
    for altura in alturas:
        paginas.append(img.crop((0, y, img.width, y + altura)).convert("RGB"))
        y += altura
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    paginas[0].save(destino, format="PDF", save_all=True,
                    append_images=paginas[1:], resolution=130.0)
    return destino


def nomes_candidatos(book: str, page: str) -> list[str]:
    """Volumes antigos nomeiam a página com 4 dígitos (`1822_0310.tif`);
    recentes sem zero à esquerda (`2625_179.tif`). Tentar as duas formas
    antes de declarar ausente."""
    p = str(page).strip()
    return [f"{book}_{int(p):04d}.tif", f"{book}_{int(p)}.tif"]


# ------------------------------------------- validação de carimbo (modelo)
PROMPT_CARIMBO = """Voce audita UMA pagina capturada do registro do condado.
Toda pagina de registro abre com o carimbo do County Clerk no TOPO, com
Doc / Bk / Vol / Pg. Arquivo em julgamento: {arquivo} (book {book}, page
{page}, pagina {n} de {total}).

Responda APENAS um objeto JSON:
{{"carimbo_no_topo": true|false,
  "book_page_do_carimbo": "<o que o carimbo diz, ex. 1822/310, ou vazio>",
  "corresponde_ao_arquivo": true|false,
  "motivo": "<UMA frase>"}}"""


def validar_carimbo(pdf: Path, *, book: str, page: str,
                    paginas: list[int] | None = None,
                    chamar: Callable[[str, bytes], str] | None = None
                    ) -> dict[str, Any]:
    """Amostra páginas renderizadas e pede o veredito ao modelo da família B
    (visão). O julgamento — é carimbo? bate com o nome? — é do modelo; aqui
    só se renderiza, envia e aplica o veredito. Sem veredito legível, a
    página fica NÃO VALIDADA (nunca aprovada por omissão)."""
    import fitz

    chamar = chamar or _chamar_visao_openai
    with fitz.open(pdf) as doc:
        total = doc.page_count
        alvo = paginas if paginas is not None else sorted(
            {1, total} | ({(total + 1) // 2} if total > 2 else set()))
        vereditos = []
        for n in alvo:
            png = doc[n - 1].get_pixmap(dpi=130).tobytes("png")
            texto = chamar(PROMPT_CARIMBO.format(
                arquivo=pdf.name, book=book, page=page, n=n, total=total), png)
            try:
                v = json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                v = {"carimbo_no_topo": False, "corresponde_ao_arquivo": False,
                     "motivo": "veredito ilegivel — pagina NAO validada"}
            vereditos.append({"pagina": n, **v})
    ok = all(v.get("carimbo_no_topo") and v.get("corresponde_ao_arquivo")
             for v in vereditos)
    return {"arquivo": pdf.name, "paginas_amostradas": len(vereditos),
            "valido": ok, "vereditos": vereditos}


def _chamar_visao_openai(prompt: str, png: bytes) -> str:
    import base64

    from dotenv import load_dotenv
    load_dotenv(".env")
    import openai
    modelo = os.environ.get("MINORH_AUDITOR_OPENAI", "gpt-4o-mini")
    resp = openai.OpenAI().chat.completions.create(
        model=modelo, max_completion_tokens=300,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url":
                "data:image/png;base64,"
                + base64.standard_b64encode(png).decode("ascii")}}]}])
    return resp.choices[0].message.content or ""


# ------------------------------------------------------ o comando coletar
def coletar(pasta: Path, *, cdp_url: str = "http://localhost:9222",
            capturador: Callable[..., tuple[bytes, list[int]]] | None = None,
            validador: Callable[..., dict[str, Any]] | None = None,
            destino: Path | None = None) -> dict[str, Any]:
    """Executa a pull list: pula o que já está no disco, captura o resto,
    corta pelas alturas, valida carimbo por amostragem, lança as aberturas.

    Regra da receita: CONFERIR O DISCO APÓS O PRIMEIRO documento, antes de
    rodar a fila — a rodada manual perdeu 40 capturas por pular isso."""
    pasta = Path(pasta)
    destino = Path(destino) if destino is not None else pasta / "FILES"
    capturador = capturador or _capturar_cdp
    validador = validador or validar_carimbo
    ledger = LedgerColeta(pasta)
    itens = ler_pull_list(pasta)

    ja, coletados, falhas, invalidos = [], [], [], []
    for i, item in enumerate(itens):
        alvo = destino / item["arquivo_alvo"]
        if alvo.exists():
            ja.append(item["arquivo_alvo"])   # no disco: nunca se reabre
            continue
        ledger.conferir_teto()
        try:
            png, alturas = capturador(item, cdp_url=cdp_url)
        except Exception as exc:
            ledger.registrar(item["arquivo_alvo"],
                             f"falha: {exc.__class__.__name__}: {exc}")
            falhas.append({"arquivo": item["arquivo_alvo"],
                           "erro": f"{exc.__class__.__name__}: {exc}"})
            continue
        ledger.registrar(item["arquivo_alvo"], "capturado")
        pdf = png_para_pdf(png, alturas, alvo)
        veredito = validador(pdf, book=item["book"], page=item["page"])
        if not veredito["valido"]:
            invalidos.append(veredito)
        coletados.append(item["arquivo_alvo"])
        if len(coletados) == 1:   # o 1o CAPTURADO nesta rodada
            if not alvo.exists() or alvo.stat().st_size == 0:
                raise SystemExit(
                    f"CONFERÊNCIA DO PRIMEIRO DOCUMENTO FALHOU: {alvo} não "
                    f"está no disco íntegro. A fila NÃO continua — regra da "
                    f"receita (40 capturas perdidas na rodada manual).")
            print(f"   primeiro documento conferido no disco: {alvo.name} "
                  f"({alvo.stat().st_size} bytes) — fila liberada")

    rel = {"pull_list": len(itens), "ja_no_disco": len(ja),
           "coletados": coletados, "falhas": falhas,
           "carimbo_invalido": invalidos,
           "aberturas": len(ledger.aberturas),
           "custo_coleta_usd": ledger.custo(),
           "completude": completude(pasta, destino)}
    (pasta / "_minorh" / "RELATORIO_COLETA.json").write_text(
        json.dumps(rel, indent=1, ensure_ascii=False), encoding="utf-8")
    return rel


def _capturar_cdp(item: dict[str, str], *, cdp_url: str
                  ) -> tuple[bytes, list[int]]:
    """A receita da ficha, sobre o Chrome CORPORATIVO já logado (CDP attach).

    Nunca digita credencial, nunca paga nada: se o site pedir login ou
    pagamento, a captura falha nomeando o pré-requisito — item de PEDIDOS.md.
    Devolve (png composto, alturas reais dos canvases)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:                   # pragma: no cover
        raise RuntimeError(
            "playwright não instalado — `pip install playwright` (o attach "
            "por CDP usa o Chrome do operador; não baixa navegador)") from exc

    import base64

    with sync_playwright() as pw:                # pragma: no cover — precisa
        browser = pw.chromium.connect_over_cdp(cdp_url)   # de Chrome vivo
        page = next(
            (p for c in browser.contexts for p in c.pages
             if "courthousedirect" in (p.url or "").lower()), None)
        if page is None:
            raise RuntimeError(
                "nenhuma aba do CourthouseDirect no Chrome (CDP "
                f"{cdp_url}) — o operador abre o Historical File Viewer "
                "logado; a automação não faz login")

        candidatos = nomes_candidatos(item["book"], item["page"])
        arquivo = None
        for nome in candidatos:
            achou = page.evaluate(
                """(nome) => {
                    const tree = $('#tree').dynatree('getTree');
                    let hit = null;
                    tree.visit(n => { if (n.data.title === nome) hit = n; });
                    if (hit) { hit.activate(); return true; }
                    return false;
                }""", nome)
            if achou:
                arquivo = nome
                break
        if arquivo is None:
            raise RuntimeError(
                f"nenhum dos nomes {candidatos} na árvore do volume "
                f"{item['book']} — declarar ausente na pull list e abrir "
                f"item de PEDIDOS.md (TexasFile/cartório)")

        page.wait_for_function(
            """(nome) => document.querySelector('#lblpath') &&
                document.querySelector('#lblpath').textContent.endsWith(nome)""",
            arg=arquivo, timeout=60000)
        frame = page.frame(name="ctl00_html5ViewerIFrame")
        if frame is None:
            raise RuntimeError("iframe ctl00_html5ViewerIFrame ausente")
        frame.wait_for_function(
            """() => {
                const cs = [...document.querySelectorAll(
                    '#viewerDocuVieware1 canvas')]
                    .filter(c => c.height > c.width &&
                                 !(c.width === 300 && c.height === 150));
                return cs.length > 0;
            }""", timeout=60000)
        zoom = frame.evaluate(
            "() => DocuViewareAPI.GetCurrentZoom('DocuVieware1')")
        largura = frame.evaluate(
            """() => [...document.querySelectorAll(
                '#viewerDocuVieware1 canvas')]
                .filter(c => c.height > c.width)[0].width""")
        if largura < LARGURA_ALVO_PX:
            frame.evaluate(
                "(z) => DocuViewareAPI.SetCurrentZoom('DocuVieware1', z)",
                zoom * (LARGURA_ALVO_PX / max(1, largura)))
            frame.wait_for_timeout(1500)

        got = frame.evaluate(
            """() => {
                const cs = [...document.querySelectorAll(
                    '#viewerDocuVieware1 canvas')]
                    .filter(c => c.height > c.width &&
                                 !(c.width === 300 && c.height === 150));
                const w = Math.max(...cs.map(c => c.width));
                const alturas = cs.map(c => c.height);
                const total = alturas.reduce((a, b) => a + b, 0);
                const comp = document.createElement('canvas');
                comp.width = w; comp.height = total;
                const ctx = comp.getContext('2d');
                let y = 0;
                for (const c of cs) { ctx.drawImage(c, 0, y); y += c.height; }
                return {png: comp.toDataURL('image/png').split(',')[1],
                        alturas: alturas};
            }""")
        return base64.standard_b64decode(got["png"]), got["alturas"]
