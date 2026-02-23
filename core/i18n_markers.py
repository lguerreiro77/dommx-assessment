# core/i18n_markers.py

class YAMLText(str):
    """
    String vinda de YAML. Continua sendo str (não quebra .strip(), f-strings, etc),
    mas serve como marcador para NÃO traduzir no wrapper.
    """
    pass


def mark_yaml_strings(obj):
    """
    Caminha por dict/list e transforma todo str em YAMLText.
    """
    if isinstance(obj, dict):
        return {k: mark_yaml_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mark_yaml_strings(v) for v in obj]
    if isinstance(obj, str) and not isinstance(obj, YAMLText):
        return YAMLText(obj)
    return obj