# Captura MITM — sesión 2026-05-20 (~16:58–17:00)

Dispositivo: `192.168.88.8` → proxy `192.168.88.20:8888`

## Endpoints observados

| Endpoint | Método | Notas |
|----------|--------|-------|
| `/IOTCommand/Run` | POST | Varios 200 OK (174b–377b). Comandos termostato. |
| `/App` | POST | Respuesta grande ~3.7k (listado cuenta/dispositivos). |
| `/app` | POST | Respuesta ~150b (variante de ruta, misma base URL). |
| `/Login` | — | **No apareció** en esta sesión (app ya autenticada con token). |

## Acciones del usuario (correlación aproximada)

| Hora local | Request | Respuesta |
|------------|---------|-----------|
| 16:58:21 | IOTCommand | 200, 174b |
| 16:58:31 | IOTCommand | 200, 377b |
| 16:59:02 | IOTCommand | 200, 163b |
| 16:59:03 | `/app` | 200, 150b |
| 16:59:07 | `/App` | 200, 3.7k |
| 16:59:31–32 | IOTCommand ×2 | 200, 174b + 251b |
| 17:00:09+ | `/App` + IOTCommand | polling app |

## Auth (pendiente de cuerpo JSON)

- No se capturaron headers/cuerpos en archivo (mitm sin `-w` en esa corrida).
- Para **security code** y **user number**: hace falta una captura con `start-mitm-capture.sh` o cerrar sesión en la app y volver a entrar mientras graba.

## Diferencias vs integración HA

1. La app usa **`POST /App`** además de login; HA solo usa dispositivos del `GET /Login`.
2. Ruta `/app` en minúsculas también aparece — conviene normalizar al probar.

## Login (17:02 local)

Secuencia observada tras logout/login en la app:

1. `GET /Login` → **200 OK, ~3.7 KB** (token + árbol `ioUser`, igual que antes)
2. `POST /App` → falló (client disconnected), reintento → **200 OK, ~3.7 KB**

No hubo llamada a ruta `/Logout` en la API (el logout parece ser solo local en la app).

Los cuerpos no quedaron guardados en esa corrida. Reiniciar captura con `mitm-zentraly-dump.py` → `docs/captures/zentraly-api.jsonl`.

## Próxima captura

```bash
./scripts/start-mitm-capture.sh
```

Luego: cerrar sesión en app → login completo → una acción (temp / off / reset).

Exportar:

```bash
/opt/homebrew/Cellar/mitmproxy/9.0.1/libexec/bin/python3.11 scripts/export-flows.py docs/captures/zentraly-*.flow
```
