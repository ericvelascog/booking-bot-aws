# Troubleshooting log

Real problems found while building this project, written down right after fixing them.

<!--
## NNN — Short title (YYYY-MM-DD)
- **Symptom:** what I saw (error message, behaviour)
- **Diagnosis:** how I narrowed it down (logs, commands, console)
- **Root cause:** what was actually wrong
- **Fix:** what I changed
- **Lesson:** what I'd check first next time
-->

## 001 — `docker` is not recognized right after installing Docker Desktop (2026-09-30)
- **Symptom:** `docker build` in PowerShell failed with *"El término 'docker' no se reconoce como nombre de un cmdlet..."* (CommandNotFoundException).
- **Diagnosis:** checked the system `PATH` stored in the registry: `C:\Program Files\Docker\Docker\resources\bin` was there, so the install was fine.
- **Root cause:** the PowerShell window had been opened *before* installing Docker. A shell reads `PATH` only once, at startup, so it never saw the new entry.
- **Fix:** closed and reopened PowerShell; `docker build` worked.
- **Lesson:** after installing any CLI tool, open a new terminal before assuming the install failed.
