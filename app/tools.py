from datetime import date, time, datetime
import calendar_service
from business_config import (
    APPOINTMENT_DURATION_MIN,
    HAS_SERVICES,
    SERVICE_NAMES,
    duration_for_service,
    MULTI_PROFESSIONAL,
    PROFESSIONAL_NAMES,
)


def _service_property() -> dict:
    """Parámetro 'service' limitado a los servicios reales de la clínica."""
    return {
        "type": "string",
        "description": "Tipo de servicio que quiere el paciente. Debe ser uno de los servicios de la clínica.",
        "enum": SERVICE_NAMES,
    }


def _professional_property() -> dict:
    """Parámetro 'professional' limitado a los fisioterapeutas de la clínica (opcional)."""
    return {
        "type": "string",
        "description": (
            "Fisioterapeuta/profesional con el que quiere la cita el paciente. "
            "Si al paciente le da igual, NO incluyas este parámetro."
        ),
        "enum": PROFESSIONAL_NAMES,
    }


# --- check_availability ---
_check_props: dict = {"date": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"}}
_check_required = ["date"]
if HAS_SERVICES:
    _check_props["service"] = _service_property()
    _check_required.append("service")
if MULTI_PROFESSIONAL:
    _check_props["professional"] = _professional_property()  # opcional

# --- create_appointment ---
_create_props: dict = {
    "client_name": {"type": "string", "description": "Nombre completo del paciente"},
    "client_phone": {"type": "string", "description": "Número de WhatsApp del paciente"},
    "date": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
    "time": {"type": "string", "description": "Hora en formato HH:MM"},
    "reason": {
        "type": "string",
        "description": (
            "Motivo de la consulta indicado por el paciente (p. ej. 'dolor lumbar', "
            "'lesión de rodilla'). Opcional: NO lo incluyas si el paciente no lo ha dicho."
        ),
    },
}
_create_required = ["client_name", "client_phone", "date", "time"]
if HAS_SERVICES:
    _create_props["service"] = _service_property()
    _create_required.append("service")
if MULTI_PROFESSIONAL:
    _create_props["professional"] = _professional_property()  # opcional

_check_desc = (
    "Consulta los horarios disponibles para reservar una cita en una fecha concreta. "
    "Úsala antes de crear una cita para mostrar al paciente las horas libres."
)
if HAS_SERVICES:
    _check_desc += " La duración de la cita depende del servicio, así que necesitas saber el servicio antes de llamarla."
if MULTI_PROFESSIONAL:
    _check_desc += " Si el paciente quiere un fisioterapeuta concreto, pásalo; si le da igual, no lo pases y se mostrará la disponibilidad de todos."

_create_desc = (
    "Crea una cita en el calendario de la clínica. "
    "Úsala solo cuando el paciente haya confirmado "
    + ("nombre, servicio, fecha y hora." if HAS_SERVICES else "nombre, fecha y hora.")
)

# Schemas de tools para Claude
TOOLS = [
    {
        "name": "check_availability",
        "description": _check_desc,
        "input_schema": {
            "type": "object",
            "properties": _check_props,
            "required": _check_required,
        },
    },
    {
        "name": "create_appointment",
        "description": _create_desc,
        "input_schema": {
            "type": "object",
            "properties": _create_props,
            "required": _create_required,
        },
    },
    {
        "name": "list_client_appointments",
        "description": "Lista las próximas citas de un paciente buscando por su número de teléfono.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_phone": {"type": "string", "description": "Número de WhatsApp del paciente"}
            },
            "required": ["client_phone"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": (
            "Cancela una cita existente. Primero usa list_client_appointments para obtener el ID, "
            "muéstrale la cita al paciente y pide confirmación antes de cancelar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "ID del evento de Google Calendar"}
            },
            "required": ["event_id"],
        },
    },
]


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Ejecuta la tool correspondiente y devuelve el resultado como string."""
    try:
        if tool_name == "check_availability":
            target = date.fromisoformat(tool_input["date"])
            duration = duration_for_service(tool_input["service"]) if HAS_SERVICES else APPOINTMENT_DURATION_MIN
            professional = tool_input.get("professional") if MULTI_PROFESSIONAL else None
            slots = calendar_service.get_free_slots_multi(target, duration, professional)
            if not slots:
                quien = f" con {professional}" if professional else ""
                return f"No hay disponibilidad{quien} el {target.strftime('%A %d/%m/%Y')} (día cerrado o sin huecos libres)."
            return f"Horas disponibles el {target.strftime('%A %d/%m/%Y')}: {', '.join(slots)}"

        elif tool_name == "create_appointment":
            target_date = date.fromisoformat(tool_input["date"])
            start_time = time.fromisoformat(tool_input["time"])
            service = tool_input.get("service", "Cita") if HAS_SERVICES else "Cita"
            duration = duration_for_service(service) if HAS_SERVICES else APPOINTMENT_DURATION_MIN
            professional = tool_input.get("professional") if MULTI_PROFESSIONAL else None
            reason = (tool_input.get("reason") or "").strip()

            event, assigned = calendar_service.book(
                client_name=tool_input["client_name"],
                client_phone=tool_input["client_phone"],
                service=service,
                target_date=target_date,
                start_time=start_time,
                duration_minutes=duration,
                professional_name=professional,
                reason=reason,
            )
            dt = datetime.fromisoformat(event["start"])
            profesional_line = f"\nFisioterapeuta: {assigned}" if (MULTI_PROFESSIONAL and assigned) else ""
            return (
                f"Cita creada correctamente.{profesional_line}\n"
                f"Fecha y hora: {dt.strftime('%A %d/%m/%Y a las %H:%M')}\n"
                f"ID de la cita: {event['id']}"
            )

        elif tool_name == "list_client_appointments":
            appointments = calendar_service.list_client_appointments_multi(tool_input["client_phone"])
            if not appointments:
                return "No se encontraron citas próximas para este paciente."
            lines = []
            for a in appointments:
                dt = datetime.fromisoformat(a["start"])
                profesional = f" | {a['profesional']}" if a.get("profesional") else ""
                lines.append(f"- {a['summary']}{profesional} | {dt.strftime('%d/%m/%Y %H:%M')} | ID: {a['id']}")
            return "Próximas citas:\n" + "\n".join(lines)

        elif tool_name == "cancel_appointment":
            success = calendar_service.cancel_appointment_multi(tool_input["event_id"])
            return "Cita cancelada correctamente." if success else "No se pudo cancelar la cita. Verifica el ID."

        else:
            return f"Tool desconocida: {tool_name}"

    except ValueError as e:
        # Hueco ya ocupado u hora/fecha mal formada: se lo decimos a Claude para
        # que ofrezca alternativas al paciente.
        return str(e)
    except Exception as e:
        import traceback
        print(f"ERROR en tool {tool_name}: {traceback.format_exc()}")
        return f"Error ejecutando {tool_name}: {str(e)}"
