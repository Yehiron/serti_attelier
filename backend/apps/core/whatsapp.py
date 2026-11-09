"""Render seguro de las plantillas editables de WhatsApp."""

import re


def render_whatsapp(template: str, *, name: str = "", sku: str = "", url: str = "") -> str:
    values = {"name": name.strip(), "sku": sku.strip(), "url": url.strip()}
    # Retirar el complemento de la plantilla predeterminada cuando no hay pieza.
    if not values["name"]:
        template = re.sub(r"\b(?:sobre|about)\s+\{name\}", "", template)

    # Quitar grupos opcionales vacíos antes de insertar valores: nunca alterar
    # paréntesis o puntuación que formen parte del nombre o de la URL.
    def group(match: re.Match[str]) -> str:
        content = match.group(0)
        fields = re.findall(r"\{([^{}]+)\}", content)
        if fields and all(not values.get(field, "") for field in fields):
            return ""
        return content

    template = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", group, template)
    template = re.sub(r"\{([^{}]+)\}", lambda m: values.get(m[1], ""), template)
    template = re.sub(r"\s+", " ", template).strip()
    template = re.sub(r"\s+([,.;:!?])", r"\1", template)
    template = re.sub(r"[,;:]+\s*([.!?])", r"\1", template)
    template = re.sub(r"^[,.;:!?\s]+", "", template)
    return template
