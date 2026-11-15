# Запуск ACE-Step API на totomoto (Windows) — выполнить на самом ноуте в PowerShell от администратора.
# Открывает порт 8001 для Tailscale и поднимает api_server с фиксами из AI-Radio.md.

# 1) Firewall: разрешить 8001 входящий (Tailscale + LAN)
netsh advfirewall firewall add rule name="ACE-Step-API-8001" dir=in action=allow protocol=TCP localport=8001 | Out-Null

# 2) Путь к ACE-Step (поправь, если другой)
$ACE = "C:\Users\yusya\ACE-Step-1.5"
Set-Location $ACE

# 3) Фиксы против OOM (ключевой: без LLM-инициализации DiT на 6GB VRAM падает)
$env:ACESTEP_INIT_LLM = "false"
$env:ACESTEP_NO_INIT = "false"
$env:PYTHONPATH = ""

# 4) Старт API (окно оставить открытым)
& "$ACE\.venv\Scripts\python.exe" -m acestep.api_server --host 0.0.0.0 --port 8001

# Проверка с этого Linux-хоста afterwards:
#   curl -s http://100.124.152.97:8001/health
