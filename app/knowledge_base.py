# La información de la clínica ya NO está aquí: vive en business_config.py
# (variable de entorno BUSINESS_CONFIG o archivo business_config.json).
from business_config import CONFIG, PROFESSIONALS

# Alias de compatibilidad por si algún módulo todavía lo importa.
BUSINESS_INFO = CONFIG


def get_business_info_text() -> str:
    """Devuelve toda la info de la clínica como texto estructurado para el system prompt."""
    b = CONFIG
    horario = "\n".join(f"  - {dia}: {hora}" for dia, hora in b.get("horario", {}).items())
    politicas = "\n".join(f"  - {k}: {v}" for k, v in b.get("politicas", {}).items())

    # Bloque de servicios y precios (solo si la clínica los tiene configurados).
    servicios_block = ""
    servicios = b.get("servicios", []) or []
    if servicios:
        lineas = []
        for s in servicios:
            linea = f"  - {s.get('nombre', '')}: {s.get('precio', '')}".rstrip()
            if s.get("duracion_min"):
                linea += f" (~{s['duracion_min']} min)"
            if s.get("descripcion"):
                linea += f" — {s['descripcion']}"
            lineas.append(linea)
        servicios_block = "\n\nSERVICIOS Y PRECIOS:\n" + "\n".join(lineas)

    # Bloque de fisioterapeutas (solo si hay varios configurados).
    profesionales_block = ""
    nombres = [x.get("nombre", "") for x in PROFESSIONALS if x.get("nombre")]
    if len(nombres) > 1:
        profesionales_block = "\n\nFISIOTERAPEUTAS: " + ", ".join(nombres)

    return f"""
INFORMACIÓN DE LA CLÍNICA:
Nombre: {b.get('nombre', '')}
Descripción: {b.get('descripcion', '')}
Teléfono: {b.get('telefono', '')}
Dirección: {b.get('direccion', '')}
Cómo llegar: {b.get('como_llegar', '')}

HORARIO:
{horario}{servicios_block}{profesionales_block}

POLÍTICAS:
{politicas}
""".strip()
