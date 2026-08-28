# -*- coding: utf-8 -*-
"""Driver do replay da WEBB B UNIT (Etapa H5) — quarentena com prova por comando.

Uso: PYTHONPATH=. python scripts/replay_webb_b.py <unidade|continuar|ship|coletar> [--continuar] [--cdp=URL]

Gabarito em quarentena: a pasta `WEBB B UNIT - Copia` INTEIRA (a ordem H diz
"a Copia é gabarito em quarentena, não fonte"), além dos padrões de sempre.
A prova (sondas + tentativas + desfecho) é gravada em `finally`, por comando.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.quarantine import QuarantineBreach, quarantined
from src.minorh import cli

UNIT = Path("C:/Users/Renato/PURPLE LAND MGMT/BKV122TX - Project Emirates/"
            "WEBB B UNIT")
COPIA_PATTERN = r".*WEBB B UNIT - Copia.*"
GABARITO_PROBES = [
    UNIT.parent / "WEBB B UNIT - Copia" / "SUBMISSION PLM"
    / "1. Landman Submitted" / "PLM Report" / "DDR - WEBB B UNIT (PLM).xlsx",
    UNIT.parent / "WEBB B UNIT - Copia" / "AUDITORIA - Webb B Unit.xlsx",
]
PROVA = UNIT / "_minorh" / "quarentena_prova.json"


def main() -> None:
    comando = sys.argv[1]
    flags = [a for a in sys.argv[2:] if a.startswith("--")]
    registro = json.loads(PROVA.read_text(encoding="utf-8")) \
        if PROVA.exists() else {"comandos": []}
    sondagem: list[dict[str, str]] = []
    bloqueios: list[str] = []
    tentativas: list[str] = []
    desfecho = "ok"

    try:
        with quarantined(allow_roots=(UNIT / "_minorh",),
                         extra_patterns=(COPIA_PATTERN,)) as tentativas:
            for alvo in GABARITO_PROBES:
                try:
                    alvo.read_bytes()
                    sondagem.append({"alvo": str(alvo),
                                     "resultado": "LEU — FALHA DA QUARENTENA"})
                except QuarantineBreach:
                    sondagem.append({"alvo": str(alvo),
                                     "resultado": "BLOQUEADO"})
            bloqueios = list(tentativas)
            tentativas.clear()

            if comando == "unidade":
                cli.cmd_unidade(UNIT)
            elif comando == "continuar":
                cli.cmd_continuar(UNIT)
            elif comando == "ship":
                cli.cmd_ship(UNIT, continuar="--continuar" in flags)
            elif comando == "coletar":
                cdp = next((a.split("=", 1)[1] for a in flags
                            if a.startswith("--cdp=")),
                           "http://localhost:9222")
                cli.cmd_coletar(UNIT, cdp)
            else:
                raise SystemExit(f"comando desconhecido: {comando}")
    except BaseException as exc:                        # noqa: BLE001
        desfecho = f"{exc.__class__.__name__}: {str(exc)[:200]}"
        raise
    finally:
        registro["comandos"].append({
            "comando": " ".join([comando] + flags),
            "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "desfecho": desfecho,
            "sondagem_deliberada": sondagem,
            "bloqueios_na_sonda": bloqueios,
            "tentativas_durante_o_run": list(tentativas),
        })
        PROVA.parent.mkdir(parents=True, exist_ok=True)
        PROVA.write_text(json.dumps(registro, indent=2, ensure_ascii=False),
                         encoding="utf-8")
        print(f"[quarentena] sonda: {len(bloqueios)} bloqueio(s) · durante o "
              f"run: {len(tentativas)} tentativa(s) · desfecho: "
              f"{desfecho[:60]} — prova em {PROVA}")


if __name__ == "__main__":
    main()
