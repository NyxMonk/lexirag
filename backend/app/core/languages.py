"""Languages supported by LexiRAG. Codes are ISO 639-1."""

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native_name": "English", "script": "Latin"},
    {"code": "hi", "name": "Hindi", "native_name": "हिन्दी", "script": "Devanagari"},
    {"code": "bn", "name": "Bengali", "native_name": "বাংলা", "script": "Bengali"},
    {"code": "mr", "name": "Marathi", "native_name": "मराठी", "script": "Devanagari"},
    {"code": "pa", "name": "Punjabi", "native_name": "ਪੰਜਾਬੀ", "script": "Gurmukhi"},
    {"code": "fr", "name": "French", "native_name": "Français", "script": "Latin"},
]

LANGUAGE_CODES = frozenset(lang["code"] for lang in SUPPORTED_LANGUAGES)
