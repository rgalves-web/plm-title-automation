"""Case File por Unit — a espinha dorsal transacional do sistema novo.

O Case File reifica o que o minorh mantinha como dict anônimo no CLI: a unit,
suas fontes (por hash), o censo documental, as afirmações com evidência, as
pesquisas e o plano de investigação — tudo em PostgreSQL local, com máquina de
estados explícita e trilha de transições.

Vertical Slice 1: `python -m src.casefile indicar "Josh B Unit"` seguido de
`planejar` produz o Unit Investigation Plan auditável; `aprovar`/`rejeitar`
fecham o gate do operador. Nenhuma linha deste pacote julga title: o modelo
afirma, o código valida forma, identidade e existência de evidência.
"""
