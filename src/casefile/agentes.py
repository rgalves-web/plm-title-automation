"""As fichas da firma de agentes (`agentes/`) como dados — carregar e validar.

Encanamento puro (ARQUITETURA_AGENTICA_v1, etapa A). O que se confere aqui:
frontmatter OKF v0.2 presente e legível, campos obrigatórios por tipo
(Role, Domain Pack, Lesson), vocabulários fechados (status, nivel_modelo),
formato de ator, referência cruzada lição → função/pacote, esquema de saída
existente e válido como JSON Schema, links internos. O que NUNCA se confere:
se a instrução da ficha é boa, se a lição é verdadeira, se o esquema é o
certo para a função — isso é julgamento, e é do operador.

Erro é nomeado e nunca corrigido em silêncio; ficha com erro é recusada.
Link interno quebrado é aviso (o OKF tolera).

Arquivos reservados (OKF v0.2): o `index.md` da raiz só pode ter
`okf_version`; `log.md` não é ficha. Um `index.md` de subpasta com `type`
no frontmatter é a ficha daquela pasta (é assim que um Domain Pack se
declara); sem frontmatter, é só listagem.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RAIZ_PADRAO = Path(__file__).resolve().parents[2] / "agentes"
PASTA_ESQUEMAS = "esquemas"

STATUS = ("draft", "stable", "deprecated")
NIVEIS_MODELO = ("forte", "medio", "barato", "barato_a_medio")
TIPOS = ("Role", "Domain Pack", "Lesson")

_ATOR_RE = re.compile(
    r"^(human:[\w.-]+|process:[\w.-]+|[\w.-]+/[\w.-]+)$")
_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_LINK_RE = re.compile(r"(?<!!)\[[^\]^][^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


@dataclass(frozen=True)
class Achado:
    codigo: str
    mensagem: str

    def __str__(self) -> str:
        return f"{self.codigo}: {self.mensagem}"


@dataclass
class Ficha:
    caminho: Path
    rel: str
    front: dict[str, Any]
    corpo: str
    tem_frontmatter: bool = False
    reservado: bool = False
    erros: list[Achado] = field(default_factory=list)
    avisos: list[Achado] = field(default_factory=list)

    @property
    def tipo(self) -> str:
        return str(self.front.get("type") or "").strip()

    @property
    def status(self) -> str:
        return str(self.front.get("status") or "").strip()

    @property
    def nome(self) -> str:
        """Identificador pelo qual outras fichas a citam: o `title` de um
        Domain Pack, o nome do arquivo de uma Role ou Lesson."""
        if self.tipo == "Domain Pack":
            return str(self.front.get("title") or "").strip()
        return self.caminho.stem

    def erro(self, codigo: str, mensagem: str) -> None:
        self.erros.append(Achado(codigo, mensagem))

    def aviso(self, codigo: str, mensagem: str) -> None:
        self.avisos.append(Achado(codigo, mensagem))


def versao(caminho: str | Path) -> str:
    """Identidade de uma ficha: sha256 dos bytes do arquivo."""
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


# --- carregar ---------------------------------------------------------------

def _ler(caminho: Path, raiz: Path) -> Ficha:
    rel = caminho.relative_to(raiz).as_posix()
    texto = caminho.read_bytes().decode("utf-8").replace("\r\n", "\n")
    m = _FRONT_RE.match(texto)
    ficha = Ficha(caminho=caminho, rel=rel, front={}, corpo=texto,
                  tem_frontmatter=bool(m))
    if m:
        try:
            front = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            ficha.erro("yaml_invalido", f"frontmatter ilegível: {exc}")
            return ficha
        if front is not None and not isinstance(front, dict):
            ficha.erro("yaml_invalido", "frontmatter não é um mapa")
            return ficha
        ficha.front = front or {}
        ficha.corpo = m.group(2)
    return ficha


def carregar(raiz: str | Path | None = None) -> list[Ficha]:
    """Todos os `.md` sob a raiz, em ordem estável."""
    raiz = Path(raiz) if raiz is not None else RAIZ_PADRAO
    if not raiz.is_dir():
        raise FileNotFoundError(f"pasta de fichas inexistente: {raiz}")
    return [_ler(p, raiz) for p in sorted(raiz.rglob("*.md"))]


# --- validar ----------------------------------------------------------------

def _presente(valor: Any) -> bool:
    if valor is None:
        return False
    if isinstance(valor, (str, list, dict)):
        return bool(valor if not isinstance(valor, str) else valor.strip())
    return True


def _exigir(ficha: Ficha, *campos: str) -> None:
    for campo in campos:
        if not _presente(ficha.front.get(campo)):
            ficha.erro(f"{campo}_ausente", f"`{campo}` obrigatório em "
                       f"{ficha.tipo or 'ficha'}")


def _ator(ficha: Ficha, onde: str, ator: Any) -> None:
    if not isinstance(ator, str) or not _ATOR_RE.match(ator.strip()):
        ficha.erro("ator_invalido",
                   f"{onde}: {ator!r} não é `agente/versao`, `human:<id>` "
                   f"nem `process:<id>`")


def _comuns(ficha: Ficha) -> None:
    f = ficha.front
    if not ficha.tipo:
        ficha.erro("type_ausente", "`type` vazio ou ausente")
    elif ficha.tipo not in TIPOS:
        ficha.aviso("type_desconhecido",
                    f"tipo {ficha.tipo!r} sem validação específica "
                    f"(conhecidos: {', '.join(TIPOS)})")
    if not ficha.status:
        ficha.erro("status_ausente", "`status` obrigatório")
    elif ficha.status not in STATUS:
        ficha.erro("status_invalido",
                   f"status {ficha.status!r} fora de {STATUS}")
    gen = f.get("generated")
    if not isinstance(gen, dict):
        ficha.erro("generated_ausente", "`generated` com `by` e `at` "
                   "obrigatório")
    else:
        if not _presente(gen.get("by")):
            ficha.erro("generated_by_ausente", "`generated.by` obrigatório")
        else:
            _ator(ficha, "generated.by", gen.get("by"))
        if not _presente(gen.get("at")):
            ficha.erro("generated_at_ausente", "`generated.at` obrigatório")
    if "verified" not in f:
        ficha.erro("verified_ausente", "`verified` obrigatório (lista, "
                   "vazia permitida)")
    elif not isinstance(f.get("verified"), list):
        ficha.erro("verified_nao_lista", "`verified` deve ser lista")
    else:
        for i, item in enumerate(f["verified"]):
            ator = item.get("by") if isinstance(item, dict) else item
            _ator(ficha, f"verified[{i}]", ator)


def _sources(ficha: Ficha) -> None:
    fontes = ficha.front.get("sources")
    if not isinstance(fontes, list) or not fontes:
        ficha.erro("sources_ausente", "`sources` deve ser lista não vazia")
        return
    for i, s in enumerate(fontes):
        if not isinstance(s, dict) or not _presente(s.get("resource")) \
                or not _presente(s.get("id")):
            ficha.erro("sources_invalido",
                       f"sources[{i}] precisa de `resource` e `id`")


def _role(ficha: Ficha, esquemas: set[str]) -> None:
    _exigir(ficha, "title", "description", "saida_esquema", "verifica")
    nivel = ficha.front.get("nivel_modelo")
    if not _presente(nivel):
        ficha.erro("nivel_modelo_ausente", "`nivel_modelo` obrigatório")
    elif nivel not in NIVEIS_MODELO:
        ficha.erro("nivel_modelo_invalido",
                   f"nivel_modelo {nivel!r} fora de {NIVEIS_MODELO}")
    if "ferramentas" not in ficha.front:
        ficha.erro("ferramentas_ausente", "`ferramentas` obrigatório")
    elif not isinstance(ficha.front["ferramentas"], list):
        ficha.erro("ferramentas_nao_lista", "`ferramentas` deve ser lista")
    esquema = ficha.front.get("saida_esquema")
    if _presente(esquema) and str(esquema) not in esquemas:
        ficha.erro("esquema_inexistente",
                   f"saida_esquema {esquema!r} sem arquivo "
                   f"{PASTA_ESQUEMAS}/{esquema}.json")


def _pack(ficha: Ficha) -> None:
    _exigir(ficha, "title", "description")
    _sources(ficha)


def _lesson(ficha: Ficha, funcoes: set[str], pacotes: set[str]) -> None:
    _exigir(ficha, "funcao", "escopo")
    funcao = ficha.front.get("funcao")
    if _presente(funcao) and str(funcao) not in funcoes:
        ficha.erro("funcao_inexistente",
                   f"funcao {funcao!r} não é Role em agentes/")
    escopo = ficha.front.get("escopo")
    if _presente(escopo):
        pacote = escopo.get("pacote") if isinstance(escopo, dict) else None
        if not _presente(pacote):
            ficha.erro("escopo_pacote_ausente", "`escopo.pacote` obrigatório")
        elif str(pacote) not in pacotes:
            ficha.erro("pacote_inexistente",
                       f"escopo.pacote {pacote!r} não é Domain Pack em "
                       f"agentes/")
    _sources(ficha)


def _index_raiz(ficha: Ficha) -> None:
    extras = sorted(set(ficha.front) - {"okf_version"})
    if extras:
        ficha.erro("index_raiz_chave_proibida",
                   f"index.md da raiz só admite `okf_version`; veio "
                   f"{extras}")
    if not _presente(ficha.front.get("okf_version")):
        ficha.erro("okf_version_ausente",
                   "index.md da raiz precisa de `okf_version`")


def _links(ficha: Ficha, raiz: Path) -> None:
    for alvo in _LINK_RE.findall(ficha.corpo):
        if re.match(r"^[a-z][a-z0-9+.-]*:", alvo, re.I) or alvo.startswith("#"):
            continue
        caminho = alvo.split("#", 1)[0]
        if not caminho:
            continue
        base = raiz if caminho.startswith("/") else ficha.caminho.parent
        if not (base / caminho.lstrip("/")).exists():
            ficha.aviso("link_quebrado", f"link interno sem destino: {alvo}")


def esquemas_disponiveis(raiz: Path) -> dict[str, Path]:
    pasta = raiz / PASTA_ESQUEMAS
    return {p.stem: p for p in sorted(pasta.glob("*.json"))} \
        if pasta.is_dir() else {}


def _validar_esquemas(raiz: Path) -> list[Achado]:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
    achados = []
    for nome, p in esquemas_disponiveis(raiz).items():
        try:
            Draft202012Validator.check_schema(
                json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, SchemaError) as exc:
            msg = getattr(exc, "message", str(exc))
            achados.append(Achado("esquema_invalido", f"{nome}.json: {msg}"))
    return achados


@dataclass
class Resultado:
    fichas: list[Ficha]
    erros_esquemas: list[Achado]

    @property
    def total_erros(self) -> int:
        return sum(len(f.erros) for f in self.fichas) + \
            len(self.erros_esquemas)

    @property
    def ok(self) -> bool:
        return self.total_erros == 0

    def por_tipo(self, tipo: str) -> list[Ficha]:
        return [f for f in self.fichas if f.tipo == tipo and not f.reservado]


def validar(raiz: str | Path | None = None) -> Resultado:
    raiz = Path(raiz) if raiz is not None else RAIZ_PADRAO
    fichas = carregar(raiz)
    esquemas = set(esquemas_disponiveis(raiz))

    for f in fichas:
        nome = f.caminho.name
        if f.rel == "index.md":
            f.reservado = True
        elif nome == "log.md":
            f.reservado = True
        elif nome == "index.md" and not f.tem_frontmatter:
            f.reservado = True
        elif not f.erros and not f.tem_frontmatter:
            f.erro("frontmatter_ausente", "ficha sem frontmatter YAML")

    cards = [f for f in fichas if not f.reservado and not f.erros]
    funcoes = {f.nome for f in cards if f.tipo == "Role"}
    pacotes = {f.nome for f in cards if f.tipo == "Domain Pack"}

    for f in fichas:
        if f.rel == "index.md":
            if not f.erros:
                _index_raiz(f)
        elif not f.reservado and not f.erros:
            _comuns(f)
            if f.tipo == "Role":
                _role(f, esquemas)
            elif f.tipo == "Domain Pack":
                _pack(f)
            elif f.tipo == "Lesson":
                _lesson(f, funcoes, pacotes)
        _links(f, raiz)
    return Resultado(fichas=fichas, erros_esquemas=_validar_esquemas(raiz))


def validar_saida(nome: str, dado: Any,
                  raiz: str | Path | None = None) -> list[str]:
    """Erros de forma de uma saída contra `esquemas/<nome>.json` (vazio = ok).
    Referências entre esquemas (`claims.json#/...`) resolvem na mesma pasta."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    raiz = Path(raiz) if raiz is not None else RAIZ_PADRAO
    todos = {n: json.loads(p.read_text(encoding="utf-8"))
             for n, p in esquemas_disponiveis(raiz).items()}
    if nome not in todos:
        raise KeyError(f"esquema {nome!r} inexistente em "
                       f"{raiz / PASTA_ESQUEMAS}")
    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in todos.values()
        if "$id" in s)
    v = Draft202012Validator(todos[nome], registry=registry)
    return [f"{'/'.join(map(str, e.absolute_path)) or '(raiz)'}: {e.message}"
            for e in sorted(v.iter_errors(dado), key=lambda e: list(
                map(str, e.absolute_path)))]


# --- CLI ----------------------------------------------------------------------

def cmd_agentes(args: list[str]) -> int:
    sub = args[0] if args else ""
    raiz = next((a.split("=", 1)[1] for a in args if a.startswith("--raiz=")),
                None)
    if sub == "validar":
        return _cmd_validar(raiz)
    if sub == "listar":
        return _cmd_listar(raiz)
    raise SystemExit("uso: python -m src.casefile agentes validar|listar "
                     "[--raiz=DIR]")


def _cmd_validar(raiz: str | None) -> int:
    r = validar(raiz)
    largura = max(len(f.rel) for f in r.fichas) if r.fichas else 10
    print(f"{'arquivo':<{largura}}  {'tipo':<12} {'status':<10} "
          f"{'erros':>5} {'avisos':>6}")
    for f in r.fichas:
        tipo = "(reservado)" if f.reservado else (f.tipo or "?")
        print(f"{f.rel:<{largura}}  {tipo:<12} {f.status or '-':<10} "
              f"{len(f.erros):>5} {len(f.avisos):>6}")
    detalhes = [(f.rel, "ERRO", a) for f in r.fichas for a in f.erros] + \
               [(f"{PASTA_ESQUEMAS}/", "ERRO", a) for a in r.erros_esquemas] + \
               [(f.rel, "aviso", a) for f in r.fichas for a in f.avisos]
    if detalhes:
        print()
        for rel, nivel, a in detalhes:
            print(f"{nivel:<5} {rel}: {a}")
    n_esq = len(esquemas_disponiveis(Path(raiz) if raiz else RAIZ_PADRAO))
    avisos = sum(len(f.avisos) for f in r.fichas)
    print(f"\n{len(r.fichas)} arquivos, {n_esq} esquemas; "
          f"{r.total_erros} erros, {avisos} avisos")
    return 0 if r.ok else 1


def _cmd_listar(raiz: str | None) -> int:
    r = validar(raiz)
    for rotulo, tipo in (("Funções", "Role"), ("Pacotes", "Domain Pack"),
                         ("Lições", "Lesson")):
        fichas = r.por_tipo(tipo)
        print(f"{rotulo} ({len(fichas)})")
        for f in fichas:
            extra = ""
            if tipo == "Role":
                extra = (f"  {f.front.get('nivel_modelo', '')}"
                         f" -> {f.front.get('saida_esquema', '')}")
            elif tipo == "Lesson":
                esc = f.front.get("escopo") or {}
                extra = (f"  {f.front.get('funcao', '')} @ "
                         f"{esc.get('pacote', '') if isinstance(esc, dict) else ''}")
            print(f"  {f.nome:<48} {f.status:<10} "
                  f"{versao(f.caminho)[:16]}{extra}")
        print()
    return 0 if r.ok else 1
