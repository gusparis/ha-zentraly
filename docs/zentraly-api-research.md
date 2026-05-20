# Investigación API Zentraly

La app oficial ([zentraly.com](https://www.zentraly.com/)) pide **email**, **contraseña**, **número de usuario** y **código de seguridad**. La integración HA hoy solo usa **email + contraseña**. Este documento aclara qué sabemos, qué falta y cómo capturar tráfico real.

## Lo que ya funciona (MITM previo)

| Campo app | ¿Usado en HA? | Dónde en la API |
|-----------|---------------|-----------------|
| Email | Sí | Header `Authorization: ztv2Auth{email}:{password}` |
| Password | Sí | Mismo header |
| User number | No explícito | Probablemente **devuelto** en `ioData.ioUser` tras login, no enviado en cada request |
| Security code | No | **Sin evidencia** en el cliente actual; hay que confirmar con nueva captura |

### `GET https://ztprdrestservicesv2.azurewebsites.net/Login`

Headers observados:

```
Authorization: ztv2Auth{email}:{password}
firebase: <base64 JSON>
User-Agent: zentralyRN/439 CFNetwork/3860.400.51 Darwin/25.3.0
Accept: application/json
```

JSON dentro de `firebase` (decodificado):

```json
{
  "ivstrUserFBToken": "<token push real en app>",
  "ivstrUserGuid": "<guid dispositivo>",
  "ivstrUserZtVersion": "7.1.3",
  "ivnroUserMobileOS": 2,
  "ivstrUserMobileTrade": "apple|android",
  "ivstrUserMobileModel": "...",
  "ivstrUserMobileOSVersion": 17,
  "ivstrUserLanguage": "es"
}
```

Logout: no hay `/Logout` en Azure; la app borra el token FCM (`fcmtoken.googleapis.com/register` con `delete=true`).

En HA usamos `ha_integration` como FCM placeholder y un GUID estable por cuenta. Auth capturado: `ztv2Auth` de 2 partes (`email:password`, len 48 en captura). Si la app envía **user number** o **security code** en otro flujo, lo más probable es:

1. **En el header `Authorization`** con más segmentos, p. ej. `ztv2Auth{email}:{password}:{securityCode}` o `...:{userNumber}`
2. **Dentro del JSON `firebase`** con claves tipo `ivnroUserNumber`, `ivstrSecurityCode`
3. **En un segundo endpoint** después de `/Login` (p. ej. `POST /App` o validación 2FA)
4. **Solo en registro / emparejamiento** de termostato, no en control diario

## Endpoints conocidos

| Ruta | Método | Uso |
|------|--------|-----|
| `/Login` | GET | Auth → JWT en `ioData.ivstrToken` + árbol `ioUser.coUbications` |
| `/App` | POST | Listado alternativo (no usado en HA; dispositivos vienen del login) |
| `/IOTCommand/Run` | POST | `getConfig`, `setConfig`, `reset` |

Tras login, comandos usan `Authorization: ztv2Token{jwt}`.

## Cuándo haría falta el security code

- Cuenta con **2FA / PIN** activado en backend.
- **Primera vinculación** del termostato (modo pairing del manual).
- Cambio de contraseña o gestión de cuenta en la app.
- Versión nueva de la app que exija un paso extra antes del JWT.

Si el login con solo email/password devuelve `numStatus: 0` y un `ivstrToken`, el código de seguridad **no es necesario para HA** en operación normal.

## Cuándo haría falta el user number

- Identificador de cuenta mostrado en la UI; suele ser **salida del servidor**, no credencial de entrada.
- Podría usarse en `POST /App` o filtros multi-usuario en hogares compartidos.
- Conviene buscar en la respuesta de login claves `ivnro*`, `ivstrUser*`, `UserNumber`.

Ejecutá:

```bash
python3 test_api.py --inspect-login
```

Eso imprime todas las claves de `ioData` / `ioUser` (sin volcar el JWT completo).

## Cómo capturar tráfico (MITM)

### Android

1. Instalar [mitmproxy](https://mitmproxy.org/) en la PC.
2. `mitmproxy -p 8080` o `mitmdump -w zentraly.flow`.
3. En el teléfono: WiFi → proxy manual → IP de la PC, puerto 8080.
4. Abrir `http://mitm.it` en el navegador del teléfono e instalar certificado CA.
5. Si la app no confía (certificate pinning), hace falta Frida o APK parcheado (avanzado).

### iOS

1. Mismo proxy; instalar perfil de mitmproxy desde `mitm.it`.
2. Ajustes → General → Información → Confianza del certificado.
3. Pinning en iOS suele ser más estricto.

### Qué registrar

Filtrar host: `ztprdrestservicesv2.azurewebsites.net`

Para cada request anotar:

- URL y método
- Header `Authorization` completo (enmascarar password al guardar)
- Header `firebase` decodificado (base64 → JSON)
- Body POST si existe
- Response: `numStatus`, primeros campos de `ioData`

### Escenarios a reproducir en la app

1. Login frío (cerrar app, abrir, ingresar email/password/**security code** si lo pide).
2. Pantalla principal con termostatos (¿polling? ¿cada cuántos segundos?).
3. Cambiar setpoint ±0.5 °C.
4. Apagar / encender termostato.
5. Agregar dispositivo (pairing) — aquí suele aparecer auth extra.
6. Cerrar sesión y volver a entrar.

## Hipótesis a validar

| # | Hipótesis | Cómo comprobarla |
|---|-----------|------------------|
| H1 | Security code va en `Authorization` como 3.er campo | Comparar header en login app vs `test_api.py` |
| H2 | Security code va en `firebase` JSON | Decodificar base64 del header en mitmproxy |
| H3 | Login es en 2 pasos (password → luego PIN) | Ver si hay 2 requests a `/Login` u otra ruta |
| H4 | User number solo aparece en response | `--inspect-login` o JSON de respuesta |
| H5 | `/App` POST requiere user number + token | Capturar body al abrir lista de dispositivos |

## Próximos pasos en el código HA

1. Volcar capturas MITM en `docs/captures/` (JSON anonimizado).
2. Si H1/H2 se confirma: ampliar `config_flow` con campos opcionales security code / user number.
3. Alinear header `firebase` con valores reales de la app (FCM token, GUID).
4. Documentar intervalo de polling de la app para igualar carga WiFi.

## Referencias en el repo

- Cliente: `custom_components/zentraly/api.py`
- Prueba local: `test_api.py --inspect-login`
- Historial git: commits `db558d4` (headers iOS), `788dabf` (sesión JWT)
