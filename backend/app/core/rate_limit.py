# backend/app/core/rate_limit.py
"""Limiter compartido entre main.py (registro del middleware/exception handler) y los
routers que aplican @limiter.limit(...) (p.ej. auth.py). Vive en un módulo propio para
evitar el import circular main.py -> api.py -> auth.py -> main.py."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
