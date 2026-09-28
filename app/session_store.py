import time

MAX_MESSAGES = 20

# Tras este tiempo sin actividad la conversación empieza de cero: evita que un
# paciente que escribe días después arrastre el contexto (y los tokens) de la
# conversación anterior.
SESSION_TTL_SECONDS = 6 * 60 * 60

# {phone_number: {"messages": [{"role": ..., "content": ...}], "last_activity": ts}}
_sessions: dict[str, dict] = {}


def get_history(phone: str) -> list[dict]:
    session = _sessions.get(phone)
    if session is None:
        return []
    if time.time() - session["last_activity"] > SESSION_TTL_SECONDS:
        clear_session(phone)
        return []
    return session["messages"]


def add_message(phone: str, role: str, content) -> None:
    session = _sessions.get(phone)
    if session is None or time.time() - session["last_activity"] > SESSION_TTL_SECONDS:
        session = {"messages": [], "last_activity": time.time()}
        _sessions[phone] = session

    session["messages"].append({"role": role, "content": content})
    session["last_activity"] = time.time()
    # Mantener solo los últimos MAX_MESSAGES para controlar tokens
    if len(session["messages"]) > MAX_MESSAGES:
        session["messages"] = session["messages"][-MAX_MESSAGES:]


def clear_session(phone: str) -> None:
    _sessions.pop(phone, None)
