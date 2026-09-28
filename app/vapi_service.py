from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import calendar_service
from business_config import (
    APPOINTMENT_DURATION_MIN as APPOINTMENT_DURATION,
    BUSINESS_HOURS,
    HAS_SERVICES,
    duration_for_service,
    MULTI_PROFESSIONAL,
)

TIMEZONE = ZoneInfo("Europe/Madrid")

_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTH_NAMES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
_HOUR_WORDS = {
    1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis",
    7: "siete", 8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce",
}


def _hour_word(h24: int) -> tuple[str, str]:
    """Devuelve (hora con artículo, franja del día) para una hora 0-23."""
    h12 = h24 % 12 or 12
    article = "la" if h12 == 1 else "las"
    if h24 < 12:
        period = "de la mañana"
    elif h24 == 12:
        period = "del mediodía"
    elif h24 < 21:
        period = "de la tarde"
    else:
        period = "de la noche"
    return f"{article} {_HOUR_WORDS[h12]}", period


def _slot_to_speech(slot: str) -> tuple[str, str]:
    """Convierte 'HH:MM' a hora hablada para TTS. Devuelve (texto, franja del día)."""
    h, m = (int(x) for x in slot.split(":"))
    if m == 45:
        base, period = _hour_word((h + 1) % 24)
        return f"{base} menos cuarto", period
    base, period = _hour_word(h)
    if m == 0:
        return base, period
    if m == 15:
        return f"{base} y cuarto", period
    if m == 30:
        return f"{base} y media", period
    return f"{base} y {m}", period


def _t2m(slot: str) -> int:
    h, m = slot.split(":")
    return int(h) * 60 + int(m)


def _m2t(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _range_speech(start_slot: str, end_slot: str) -> tuple[str, str]:
    """'de las dos a las cinco de la tarde' (la franja solo se repite si cambia)."""
    start_txt, start_period = _slot_to_speech(start_slot)
    end_txt, end_period = _slot_to_speech(end_slot)
    if start_period != end_period:
        start_txt = f"{start_txt} {start_period}"
    return f"de {start_txt} a {end_txt} {end_period}", end_period


def _slots_to_speech(slots: list[str], step_min: int) -> str:
    """Huecos en formato hablado, agrupando tramos consecutivos en rangos.

    Tramos de 3+ huecos seguidos se dicen como rango ("de las cinco a las nueve");
    huecos sueltos se dicen uno a uno. La franja del día solo se dice al cambiar.
    """
    # Partir en tramos consecutivos (cada hueco empieza donde acaba el anterior).
    runs: list[list[str]] = [[slots[0]]]
    for s in slots[1:]:
        if _t2m(s) - _t2m(runs[-1][-1]) == step_min:
            runs[-1].append(s)
        else:
            runs.append([s])

    parts = []
    last_period = None
    for run in runs:
        if len(run) >= 3:
            end_slot = _m2t(_t2m(run[-1]) + step_min)  # fin de la última cita del tramo
            text, last_period = _range_speech(run[0], end_slot)
            parts.append(text)
        else:
            for s in run:
                text, period = _slot_to_speech(s)
                if period != last_period:
                    text = f"{text} {period}"
                    last_period = period
                parts.append(text)
    return ", ".join(parts)


def _free_slots_speech(free_slots: list[str], step_min: int, target_date: date) -> str:
    """Frase completa de disponibilidad para voz, con caso especial de día entero libre."""
    hours = BUSINESS_HOURS.get(target_date.weekday())
    equivalencias = (
        f" (Inicios exactos SOLO para las herramientas, no los digas: "
        f"{', '.join(free_slots)}.)"
    )

    # ¿Día entero libre? Un solo tramo que va de la apertura al cierre.
    if hours:
        open_min = hours[0].hour * 60 + hours[0].minute
        close_min = hours[1].hour * 60 + hours[1].minute
        contiguous = all(
            _t2m(b) - _t2m(a) == step_min for a, b in zip(free_slots, free_slots[1:])
        )
        if (
            contiguous
            and _t2m(free_slots[0]) == open_min
            and _t2m(free_slots[-1]) + step_min == close_min
        ):
            rango, _ = _range_speech(free_slots[0], _m2t(close_min))
            return f"Tenemos todo el día libre, {rango}.{equivalencias}"

    return f"Huecos disponibles: {_slots_to_speech(free_slots, step_min)}.{equivalencias}"


def _parse_vapi_datetime(dt_str: str) -> tuple[date, time]:
    """Parsea 'YYYY/MM/DD HH:MM' de VAPI a date y time."""
    dt = datetime.strptime(dt_str.strip(), "%Y/%m/%d %H:%M")
    return dt.date(), dt.time()


def _duration(service_type: str) -> int:
    """Duración según el servicio (si la clínica los distingue) o la duración por defecto."""
    if HAS_SERVICES and service_type:
        return duration_for_service(service_type)
    return APPOINTMENT_DURATION


def _professional_arg(args: dict) -> str | None:
    """Lee el profesional del payload de VAPI ('professional', con fallback al antiguo 'barber')."""
    if not MULTI_PROFESSIONAL:
        return None
    value = (args.get("professional") or args.get("barber") or "").strip()
    return value or None


def handle_check_availability(args: dict) -> str:
    """
    Devuelve los huecos libres del día ya calculados.
    El LLM solo tiene que leerlos, sin hacer aritmética.
    """
    try:
        preferred_dt = args.get("preferredDateTime", "")
        target_date, req_time = _parse_vapi_datetime(preferred_dt)

        duration = _duration(args.get("serviceType", ""))
        professional = _professional_arg(args)
        free_slots = calendar_service.get_free_slots_multi(target_date, duration, professional)

        if not free_slots:
            # El horario sale de la configuración de la clínica, no está hardcodeado:
            # si ese día de la semana no tiene horario, está cerrado.
            if BUSINESS_HOURS.get(target_date.weekday()) is None:
                day_name = _DAY_NAMES[target_date.weekday()]
                return f"El {day_name} la clínica está cerrada. ¿Te viene bien otro día?"
            return "Lo siento, ese día no hay huecos disponibles. ¿Te viene bien otro día?"

        # Forma hablada (con tramos agrupados) para que el TTS no deletree "14:30";
        # los inicios exactos van aparte porque bookAppointment necesita HH:MM.
        return _free_slots_speech(free_slots, duration, target_date)

    except Exception as e:
        import traceback
        print(f"ERROR vapi check_availability: {traceback.format_exc()}")
        return f"Error al consultar disponibilidad: {str(e)}"


def handle_book_appointment(args: dict) -> str:
    try:
        name = args.get("name", "").strip()
        phone = args.get("phone", "").strip()
        service_type = args.get("serviceType", "").strip()
        preferred_dt = args.get("preferredDateTime", "")
        professional = _professional_arg(args)
        reason = (args.get("reason") or args.get("motivo") or "").strip()

        target_date, start_time = _parse_vapi_datetime(preferred_dt)

        duration = _duration(service_type)
        service_label = service_type if (HAS_SERVICES and service_type) else "Cita"

        event, assigned = calendar_service.book(
            client_name=name,
            client_phone=phone,
            service=service_label,
            target_date=target_date,
            start_time=start_time,
            duration_minutes=duration,
            professional_name=professional,
            reason=reason,
        )

        dt = datetime.fromisoformat(event["start"]).astimezone(TIMEZONE)
        con_profesional = f" con {assigned}" if (MULTI_PROFESSIONAL and assigned) else ""
        hora_hablada, franja = _slot_to_speech(dt.strftime("%H:%M"))
        fecha_hablada = f"el {_DAY_NAMES[dt.weekday()]} {dt.day} de {_MONTH_NAMES[dt.month - 1]}"
        return (
            f"Cita confirmada. "
            f"{service_label} para {name}{con_profesional} {fecha_hablada} a {hora_hablada} {franja}. "
            f"Teléfono registrado: {phone}."
        )

    except calendar_service.SlotUnavailableError as e:
        # Hueco ya ocupado: alternativas en formato hablado para el TTS.
        if e.free_slots:
            return "Esa hora ya no está disponible. " + _free_slots_speech(e.free_slots, duration, target_date)
        return "Esa hora ya no está disponible y no quedan huecos ese día. ¿Te viene bien otro día?"
    except Exception as e:
        import traceback
        print(f"ERROR vapi book_appointment: {traceback.format_exc()}")
        return f"Error al crear la cita: {str(e)}"


def handle_cancel_appointment(args: dict) -> str:
    try:
        phone = args.get("phone", "").strip()

        appointments = calendar_service.list_client_appointments_multi(phone)

        if not appointments:
            return "No se encontró ninguna cita asociada a ese teléfono."

        # Cancelar la primera cita encontrada (la más próxima)
        event_id = appointments[0]["id"]
        summary = appointments[0]["summary"]
        success = calendar_service.cancel_appointment_multi(event_id)

        if success:
            return f"Cita cancelada correctamente: {summary}."
        else:
            return "No se pudo cancelar la cita. Por favor, inténtalo de nuevo."

    except Exception as e:
        import traceback
        print(f"ERROR vapi cancel_appointment: {traceback.format_exc()}")
        return f"Error al cancelar la cita: {str(e)}"


HANDLERS = {
    "checkAvailability": handle_check_availability,
    "bookAppointment": handle_book_appointment,
    "cancelAppointment": handle_cancel_appointment,
}


def process_vapi_request(body: dict) -> dict:
    """Punto de entrada principal. Procesa el payload de VAPI y devuelve la respuesta."""
    try:
        tool_calls = body.get("message", {}).get("toolCallList", [])

        if not tool_calls:
            # Algunos eventos de VAPI no son tool calls (status updates, etc.)
            return {}

        results = []
        for call in tool_calls:
            call_id = call.get("id", "")
            function_name = call.get("function", {}).get("name", "")
            arguments = call.get("function", {}).get("arguments", {})

            # Arguments puede venir como string JSON o como dict
            if isinstance(arguments, str):
                import json
                arguments = json.loads(arguments)

            handler = HANDLERS.get(function_name)
            if handler:
                result_text = handler(arguments)
            else:
                result_text = f"Función desconocida: {function_name}"

            results.append({"toolCallId": call_id, "result": result_text})

        return {"results": results}

    except Exception as e:
        import traceback
        print(f"ERROR procesando request VAPI: {traceback.format_exc()}")
        return {"results": []}
