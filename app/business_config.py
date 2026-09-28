# -*- coding: utf-8 -*-
"""
Cargador de la configuración del negocio (clínica de fisioterapia / osteopatía).

Toda la información específica de cada cliente (nombre, horario, servicios,
políticas, etc.) vive AQUÍ como datos, no en el código. Así el mismo código
sirve para todas las clínicas y solo cambia esta configuración.

Origen de los datos (por orden de prioridad):
  1. Variable de entorno BUSINESS_CONFIG  -> JSON completo (PRODUCCIÓN / por cliente)
  2. Archivo local business_config.json   -> usado en desarrollo y como demo

Para un cliente real NO se edita el código: se rellena el JSON y se pega en la
variable de entorno BUSINESS_CONFIG de su despliegue en Railway.
"""
import os
import json
import unicodedata
from datetime import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_DAY_TO_INT = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}

_CLOSED_WORDS = {"cerrado", "closed", "none", "null", ""}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _load_raw() -> dict:
    """Carga el JSON de configuración desde la variable de entorno o el archivo."""
    content = os.environ.get("BUSINESS_CONFIG")
    if content:
        print(">>> business_config: cargado desde la variable de entorno BUSINESS_CONFIG")
        return json.loads(content)

    path = os.path.join(BASE_DIR, "business_config.json")
    print(f">>> business_config: cargado desde archivo local ({path})")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_hours(horario: dict) -> dict:
    """Convierte el horario en texto a {0..6: (inicio, fin) | None} para la lógica de huecos."""
    result: dict[int, tuple[time, time] | None] = {i: None for i in range(7)}
    for day, value in (horario or {}).items():
        idx = _DAY_TO_INT.get(_strip_accents(str(day)).strip().lower())
        if idx is None:
            continue
        norm = _strip_accents(str(value)).strip().lower() if value is not None else ""
        if norm in _CLOSED_WORDS:
            result[idx] = None
            continue
        # Normaliza guiones y espacios: "14:00 - 20:00" -> "14:00-20:00"
        clean = str(value).replace("–", "-").replace("—", "-").replace(" ", "")
        parts = clean.split("-")
        if len(parts) != 2:
            result[idx] = None
            continue
        try:
            result[idx] = (time.fromisoformat(parts[0]), time.fromisoformat(parts[1]))
        except ValueError:
            result[idx] = None
    return result


# ------------------------------------------------------------------ API pública
CONFIG: dict = _load_raw()

BUSINESS_HOURS: dict[int, tuple[time, time] | None] = _parse_hours(CONFIG.get("horario", {}))

# Duración por defecto cuando la clínica NO distingue servicios.
APPOINTMENT_DURATION_MIN: int = int(CONFIG.get("duracion_cita_min", 45))

IS_DEMO: bool = bool(CONFIG.get("demo", False))

# ----- Servicios y duraciones -----------------------------------------------
# Lista de servicios de la clínica (vacía = no se distingue por servicio).
SERVICES: list[dict] = CONFIG.get("servicios", []) or []
HAS_SERVICES: bool = len(SERVICES) > 0
# Nombres tal cual para mostrarlos y para el enum de las tools.
SERVICE_NAMES: list[str] = [s["nombre"] for s in SERVICES if s.get("nombre")]

# Mapa nombre-normalizado -> duración en minutos.
_SERVICE_DURATIONS: dict[str, int] = {
    _strip_accents(s["nombre"]).strip().lower(): int(s.get("duracion_min", APPOINTMENT_DURATION_MIN))
    for s in SERVICES
    if s.get("nombre")
}


def duration_for_service(service_name: str) -> int:
    """Devuelve la duración (min) del servicio indicado, o la duración por defecto."""
    if not service_name:
        return APPOINTMENT_DURATION_MIN
    return _SERVICE_DURATIONS.get(
        _strip_accents(str(service_name)).strip().lower(), APPOINTMENT_DURATION_MIN
    )


# ----- Fisioterapeutas / profesionales (multi-calendario) --------------------
# Lista de profesionales, cada uno con su propio calendario (vacía = un solo calendario).
# Se aceptan las claves "profesionales" y "fisioterapeutas" en el JSON.
PROFESSIONALS: list[dict] = (
    CONFIG.get("profesionales") or CONFIG.get("fisioterapeutas") or []
)
HAS_PROFESSIONALS: bool = len(PROFESSIONALS) > 0
MULTI_PROFESSIONAL: bool = len(PROFESSIONALS) > 1  # solo se pregunta "¿con quién?" si hay más de uno
PROFESSIONAL_NAMES: list[str] = [p["nombre"] for p in PROFESSIONALS if p.get("nombre")]


def calendar_for_professional(professional_name: str) -> str | None:
    """Devuelve el calendar_id del profesional indicado (None si no se encuentra)."""
    if not professional_name:
        return None
    target = _strip_accents(str(professional_name)).strip().lower()
    for p in PROFESSIONALS:
        if _strip_accents(str(p.get("nombre", ""))).strip().lower() == target:
            return p.get("calendar_id")
    return None
