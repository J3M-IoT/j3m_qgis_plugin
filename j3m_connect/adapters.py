# SPDX-License-Identifier: GPL-3.0-or-later
"""Provisional presentation adapters; no J3M business rules."""

import json


def session_choices(payload):
    """Return internal (identifier, label) pairs. Adapt here to the real contract."""
    if payload is None or payload == []:
        return []
    if not isinstance(payload, list):
        raise ValueError("Formato de sessões ainda não integrado. Adapte session_choices em adapters.py ao contrato real.")
    choices = []
    seen = set()
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, (str, int)) or not str(item).strip():
            raise ValueError("A adaptação provisória aceita apenas identificadores textuais/inteiros. Ajuste session_choices ao retorno real.")
        identifier = str(item)
        if identifier in (".", "..") or any(ord(char) < 32 for char in identifier):
            raise ValueError("A resposta contém um identificador de sessão inválido.")
        if identifier in seen:
            raise ValueError("A resposta contém identificadores de sessão duplicados.")
        seen.add(identifier)
        choices.append((identifier, identifier))
    return choices


def indicator_text(payload):
    """Display the response dynamically until a presentation contract exists."""
    if payload is None or payload == {} or payload == []:
        return "Nenhum indicador disponível."
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
