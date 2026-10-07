from datetime import time

from business_config import APPOINTMENT_DURATION_MIN, _parse_hours, duration_for_service


def test_parse_hours_reads_open_and_closed_days():
    hours = _parse_hours({"lunes": "14:00 - 20:00", "sabado": "Cerrado"})

    assert hours[0] == (time(14, 0), time(20, 0))  # 0 = lunes
    assert hours[5] is None                        # sábado: cerrado
    assert hours[6] is None                        # domingo no aparece: cerrado


def test_parse_hours_accepts_accents_and_long_dashes():
    hours = _parse_hours({"Miércoles": "09:00 – 14:00"})

    assert hours[2] == (time(9, 0), time(14, 0))


def test_service_duration_ignores_accents_and_case():
    # Según business_config.json, la osteopatía dura 60 minutos
    assert duration_for_service("Osteopatía") == 60
    assert duration_for_service("osteopatia") == 60


def test_unknown_service_uses_default_duration():
    assert duration_for_service("Masaje con piedras") == APPOINTMENT_DURATION_MIN
