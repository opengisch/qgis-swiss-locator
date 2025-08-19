import os

from swiss_locator import DEBUG as _DEBUG
from swiss_locator.core.language import AVAILABLE_LANGUAGES

DEBUG = _DEBUG
PLUGIN_DIR = os.path.dirname(__file__)
_AVAILABLE_LOCALES = set(AVAILABLE_LANGUAGES)
