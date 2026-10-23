# SPDX-License-Identifier: GPL-3.0-or-later
"""Plugin-owned translations, independent of the application's translators.

Only display text is translated: API keys, observations and field names remain
unchanged. Catalogs are loaded once; workers read the selected catalog only.
"""
import json
from pathlib import Path

from qgis.PyQt.QtCore import QLocale
from qgis.core import QgsApplication, QgsSettings

LANGUAGES = ('pt-br', 'en-us', 'es-es')
LANGUAGE_KEY = 'J3MConnect/language'
_language = 'en-us'
_catalogs = {
    code: json.loads((Path(__file__).with_name('i18n') / (code + '.json')).read_text(encoding='utf-8'))
    for code in ('en-us', 'es-es')
}


def resolve_language(value):
    """Use the backend's exact locales, or English for unsupported locales."""
    value = str(value or '').strip().lower().replace('_', '-')
    # QGIS may store only the base language for these bundled translations.
    return {'pt': 'pt-br', 'en': 'en-us', 'es': 'es-es'}.get(
        value, value if value in LANGUAGES else 'en-us')


def qgis_language():
    app = QgsApplication.instance()
    if app is not None and app.translation():
        return resolve_language(app.translation())
    settings = QgsSettings()
    if settings.value('locale/overrideFlag', False, type=bool):
        return resolve_language(settings.value('locale/userLocale', '', type=str))
    return resolve_language(QLocale().name())


def initialize():
    global _language
    choice = QgsSettings().value(LANGUAGE_KEY, '', type=str)
    _language = resolve_language(choice) if choice else qgis_language()


def language():
    return _language


def set_language(choice):
    """Persist an explicit choice; an empty choice follows QGIS again."""
    if choice and choice not in LANGUAGES:
        raise ValueError('Unsupported plugin language')
    QgsSettings().setValue(LANGUAGE_KEY, choice)
    initialize()


def tr(source):
    if _language == 'pt-br':
        return source
    return _catalogs[_language].get(source, _catalogs['en-us'].get(source, source))


def value_label(field, value):
    """Translate documented enum values for display, retaining unknown values."""
    labels = {
        'timePeriod': {'day': 'Dia', 'night': 'Noite'},
        'direction': {'rise': 'Subida', 'drop': 'Queda'},
        'mode': {'online': 'Online', 'offline': 'Offline'},
        'status': {'online': 'Online', 'offline': 'Offline'},
    }
    source = labels.get(field, {}).get(str(value))
    return tr(source) if source else str(value)


initialize()
