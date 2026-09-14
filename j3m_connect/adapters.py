# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation adapters for the integration API; no business rules."""

import json


def _response_data(payload):
    if payload is None:
        return None
    if not isinstance(payload, dict) or payload.get("success") is not True or "data" not in payload:
        raise ValueError("Resposta inválida: esperado um objeto com success=true e data.")
    return payload["data"]


def session_choices(payload):
    """Use the session UUID for requests and its name for presentation."""
    sessions = _response_data(payload)
    if sessions is None:
        return []
    if not isinstance(sessions, list):
        raise ValueError("Resposta inválida: data deve conter uma lista de sessões.")
    choices = []
    seen = set()
    for item in sessions:
        if not isinstance(item, dict) or not isinstance(item.get("uuid"), str) or not item["uuid"].strip():
            raise ValueError("A resposta contém uma sessão sem UUID válido.")
        identifier = item["uuid"].strip()
        if identifier in (".", "..") or any(ord(char) < 32 for char in identifier):
            raise ValueError("A resposta contém um identificador de sessão inválido.")
        if identifier in seen:
            raise ValueError("A resposta contém identificadores de sessão duplicados.")
        seen.add(identifier)
        label = item.get("name")
        choices.append((identifier, label.strip() if isinstance(label, str) and label.strip() else identifier))
    return choices


def indicator_text(payload):
    """Display all returned indicator fields, including unknown/optional ones."""
    payload = _response_data(payload)
    if payload is None or payload == {} or payload == []:
        return "Nenhum indicador disponível."
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
