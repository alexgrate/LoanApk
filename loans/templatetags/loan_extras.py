from django import template

register = template.Library()


@register.filter
def dictkey(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key, "")
    return ""


@register.filter
def get(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key, "")
    return getattr(mapping, key, "")
