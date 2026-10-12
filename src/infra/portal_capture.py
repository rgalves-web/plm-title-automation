"""Historical portal IO extracted for replay compatibility."""
import io, json, os
from pathlib import Path
from typing import Any, Callable
CUSTO_ABERTURA_USD = 0.50
LARGURA_ALVO_PX = 1150

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
