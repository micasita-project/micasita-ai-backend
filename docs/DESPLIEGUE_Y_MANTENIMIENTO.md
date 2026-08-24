# 4.2.5 Despliegue

El sistema **MiCasita** está compuesto por dos artefactos desplegables de manera independiente:

| Componente | Tecnología | Entorno de producción |
|---|---|---|
| **Backend (API + IA)** | Python 3.11 · FastAPI · PostgreSQL + PostGIS · XGBoost | Render (Web Service) |
| **Aplicación Móvil** | React Native 0.81 · Expo SDK 54 · TypeScript | Expo (Android / iOS) |

Ambos consumen además servicios externos: **Cloudinary** (imágenes), **SendGrid** (correos transaccionales), **OSRM** (ruteo), **OpenStreetMap** (tiles de mapa) y **Nominatim / Photon** (geocodificación).

---

## 4.2.5.1 Guía de Instalación / Despliegue

### A. Backend — Entorno Local (Desarrollo)

#### Requisitos previos
- **Python 3.11.0** (fijado en `.python-version`; recomendado para evitar problemas de compilación de XGBoost y dependencias nativas).
- **PostgreSQL** con la extensión **PostGIS** habilitada.
- **Git**.

#### Pasos de instalación

1. **Clonar el repositorio** e ingresar a la carpeta del proyecto.

2. **Crear y activar el entorno virtual:**
   ```bash
   # macOS / Linux
   python3.11 -m venv venv
   source venv/bin/activate

   # Windows (PowerShell)
   py -3.11 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Instalar dependencias:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno:** copiar `.env.example` a `.env` y completar los valores (ver tabla en la sección de Administración).

5. **Verificar PostgreSQL en ejecución** y que exista la base `micasita_db` (por defecto el proyecto espera usuario `postgres` / contraseña `postgres`).

6. **Poblar la base de datos (opcional, recomendado en desarrollo):**
   ```bash
   # macOS / Linux
   export PYTHONPATH=.
   python scripts/seed_db.py

   # Windows (PowerShell)
   $env:PYTHONPATH="."
   python scripts/seed_db.py
   ```
   Esto crea el usuario administrador por defecto `admin@micasita.ai` (contraseña `password123`) y carga las propiedades de ejemplo.

7. **Iniciar la API:**
   ```bash
   uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0
   ```
   La API queda disponible en `http://127.0.0.1:8000` (y en la IP local de la máquina para probar desde dispositivos físicos/emuladores). La documentación interactiva se genera automáticamente en `http://127.0.0.1:8000/docs` (Swagger UI).

> Al arrancar, la aplicación habilita la extensión PostGIS (`CREATE EXTENSION IF NOT EXISTS postgis`) y crea las tablas que falten (`Base.metadata.create_all`).

#### Backend — Entorno de Producción (Render)

El despliegue está definido como **Infraestructura como Código** en `render.yaml`:

```yaml
services:
  - type: web
    name: micasita-ai-backend
    runtime: python
    region: oregon
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Flujo de despliegue (Continuous Deployment):**
1. Conectar el repositorio de GitHub al servicio Web de Render.
2. Render detecta `render.yaml` y aplica `buildCommand` (instalación de dependencias) y `startCommand` (arranque del servidor).
3. Configurar **todas las variables de entorno** en el panel de Render (Environment), ya que están marcadas como `sync: false` (no se versionan por seguridad).
4. Aprovisionar una base de datos **PostgreSQL gestionada por Render** y enlazar su `DATABASE_URL` (interna para el servicio, externa para conexiones desde fuera).
5. Cada `git push` a la rama principal dispara un nuevo build y despliegue automático.

> `render.yaml` declara todas las variables vigentes (`PYTHON_VERSION`, `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, las tres de Cloudinary, `SENDGRID_API_KEY`, `SENDGRID_EMAIL_SENDER` y `USD_TO_PEN`), todas con `sync: false` para no versionar secretos.

---

### B. Aplicación Móvil — Entorno Local (Desarrollo)

#### Requisitos previos
- **Node.js** (LTS) y **npm**.
- **Expo CLI** (se ejecuta vía `npx`, no requiere instalación global).
- App **Expo Go** en un dispositivo físico, o un **emulador Android / simulador iOS**.

#### Pasos de instalación

1. **Instalar dependencias:**
   ```bash
   npm install
   ```

2. **Configurar variables de entorno:** copiar `.env.example` a `.env` y definir los endpoints públicos (prefijo obligatorio `EXPO_PUBLIC_`):
   ```
   EXPO_PUBLIC_API_BASE_URL=<URL del backend>
   EXPO_PUBLIC_OSM_TILE_URL=<URL de tiles de OpenStreetMap>
   EXPO_PUBLIC_OSRM_DRIVING_URL=<URL OSRM perfil auto>
   EXPO_PUBLIC_OSRM_CYCLING_URL=<URL OSRM perfil bicicleta>
   EXPO_PUBLIC_OSRM_WALKING_URL=<URL OSRM perfil a pie>
   ```
   Estas variables se centralizan en `shared/config/env.ts`.

3. **Iniciar el servidor de desarrollo:**
   ```bash
   npx expo start
   ```
   Desde la consola se puede abrir la app en Expo Go (escaneando el QR), en un emulador Android o en un simulador iOS.

#### Aplicación Móvil — Generación de Binarios (Producción)

- **Identificadores de la app** (`app.json`): `name` = "Mi Casita", `slug` = `micasita_app`, `bundleIdentifier`/`package` = `pe.edu.upc.micasita`, versión `1.0.0`.
- Está habilitada la **New Architecture** (`newArchEnabled: true`), el **React Compiler** y las **rutas tipadas** (`typedRoutes`).
- El repositorio ya contiene las carpetas nativas `android/` e `ios/` (proyecto *prebuild*), por lo que se puede compilar:
  ```bash
  npx expo run:android   # APK/AAB de desarrollo
  npx expo run:ios       # build iOS
  ```
- Para distribución en tiendas (Google Play / App Store) se recomienda configurar **EAS Build** (`eas.json` aún no presente en el repositorio).

---

## 4.2.5.2 Guía de Usuario

Manual para el usuario final de la aplicación móvil **Mi Casita**.

### 1. Modo Invitado (sin cuenta)
Al abrir la app por primera vez no es obligatorio registrarse. El usuario invitado puede:
- Explorar el catálogo de viviendas aprobadas.
- Configurar su búsqueda (dirección de casa, lugar de trabajo, presupuesto y modo de transporte) y obtener **recomendaciones de IA** mediante el botón "Generar recomendaciones".
- Visualizar resultados en el mapa con rutas multimodales (auto, bicicleta, a pie).

Los datos de invitado se guardan localmente en el dispositivo y se transfieren automáticamente a la cuenta si el usuario decide registrarse.

### 2. Registro y Verificación de Correo
1. Crear una cuenta con correo, contraseña, nombre y apellido.
2. El sistema envía un **código OTP de 6 dígitos** al correo registrado.
3. En la pantalla de verificación, ingresar el código (las casillas avanzan solas al escribir y admiten pegar el código completo).
4. Si el código expiró, usar **"Reenviar código"**.
5. Una vez verificado, se inicia sesión automáticamente. **No se puede iniciar sesión con un correo sin verificar.**

### 3. Inicio de Sesión y Recuperación de Contraseña
- **Iniciar sesión** con correo y contraseña.
- **¿Olvidaste tu contraseña?** (en la pantalla de login):
  1. Ingresar el correo → se envía un OTP.
  2. Ingresar el OTP + la nueva contraseña.
  3. Volver a iniciar sesión con la nueva contraseña.

### 4. Funcionalidades para Usuarios Autenticados
- **Recomendaciones IA personalizadas** por lugar de trabajo, con cálculo de tiempo de viaje y ahorro de tiempo (`time_saved_mins`).
- **Favoritos:** marcar/desmarcar viviendas con el corazón y consultarlas en "Mis Favoritos".
- **Publicar vivienda:** asistente paso a paso con carga de fotos (almacenadas en Cloudinary). Las publicaciones quedan en estado *pendiente* hasta su moderación.
- **Mis publicaciones:** seguimiento del estado (pendiente / aprobada / rechazada con motivo).
- **Perfil → Editar perfil:**
  - Actualizar nombre y apellido.
  - **Cambiar contraseña** (con sesión activa): requiere la contraseña actual y la nueva.
- **Lugares de trabajo y vivienda actual:** administrar direcciones usadas para las recomendaciones.

### 5. Notificaciones por Correo
El usuario recibe correos automáticos ante: verificación de cuenta, recuperación de contraseña y resultado de moderación de sus publicaciones (aprobada / rechazada).

---

## 4.2.5.3 Guía de Administración

Dirigida al administrador del sistema y al rol **admin** de la plataforma.

### 1. Configuración (Variables de Entorno)

**Backend** (`.env` / panel de Render):

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | Cadena de conexión a PostgreSQL + PostGIS. |
| `SECRET_KEY` | Clave para firmar los tokens JWT. **Crítica.** |
| `ALGORITHM` | Algoritmo JWT (`HS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Vigencia de sesión (10080 = 7 días). |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Credenciales de Cloudinary (imágenes). |
| `SENDGRID_API_KEY` | API Key de SendGrid (envío de correos). |
| `SENDGRID_EMAIL_SENDER` | Remitente verificado en SendGrid. |
| `USD_TO_PEN` | Tipo de cambio para normalizar precios. |
| `PYTHON_VERSION` | Versión de Python en Render. |

**Móvil** (`.env`, prefijo `EXPO_PUBLIC_`): `API_BASE_URL`, `OSM_TILE_URL`, `OSRM_DRIVING_URL`, `OSRM_CYCLING_URL`, `OSRM_WALKING_URL`.

### 2. Servicios Externos a Administrar
- **SendGrid:** plan gratuito limitado a ~100 correos/día. Requiere un **Single Sender verificado** o, idealmente, **autenticación de dominio (SPF/DKIM/DMARC)** para evitar que los correos caigan en spam (especialmente en servidores institucionales).
- **Cloudinary:** administración del almacenamiento y cuotas de imágenes.
- **OSRM / OpenStreetMap / Nominatim / Photon:** servicios públicos con políticas de uso y límites de tasa; monitorear disponibilidad.
- **Render:** en plan *free* el servicio se suspende tras inactividad (arranques en frío) y la base de datos gestionada tiene límites de almacenamiento y retención.

### 3. Gestión de la Base de Datos

- **Esquema:** se sincroniza al arrancar con `Base.metadata.create_all`, que **crea las tablas faltantes** (p. ej. una tabla nueva como `otp_codes` se crea sola en el siguiente deploy). **Importante:** este mecanismo **no agrega columnas a tablas que ya existen**.
- **Migraciones:** para cambios sobre tablas existentes se usan scripts idempotentes en `scripts/`, p. ej.:
  - `migrate_email_verified.py` — agrega la columna `email_verified` a `users`.
  - `migrate_otp_codes.py` — crea la tabla `otp_codes` (almacén persistente de OTP).
  - `migrate_postgis.py`, `migrate_create_favorites_table.py`, `migrate_phone.py`, etc.

  Patrón usado: `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`, seguro de re-ejecutar.
- **Ejecución de una migración contra producción** (sobreescribiendo la URL de la base):
  ```bash
  DATABASE_URL="<EXTERNAL_DATABASE_URL>" python scripts/migrate_otp_codes.py
  ```
- **Almacén de OTP:** los códigos de verificación y recuperación se guardan en la tabla **`otp_codes`** (no en memoria), por lo que sobreviven reinicios del servidor y son consistentes entre múltiples instancias. La expiración se controla por el campo `expires_at` (15 min para reset de contraseña, 24 h para verificación de correo) y cada código es de un solo uso.
- **Usuario administrador inicial:** `admin@micasita.ai` (creado por `scripts/seed_db.py`). Por seguridad, su contraseña debe cambiarse del valor por defecto en producción.

### 4. Panel de Administración (rol `admin`)
El usuario con rol `admin` (a través de la propia app móvil) puede:
- **Moderar propiedades:** aprobar o rechazar publicaciones (con motivo de rechazo). Cada acción dispara un correo automático al publicador vía SendGrid.
- **Gestionar usuarios:** activar/bloquear cuentas (`is_active`); las cuentas bloqueadas no pueden iniciar sesión.

### 5. Respaldo (Backup)
- **Base de datos:** programar respaldos periódicos de PostgreSQL (Render ofrece copias según el plan; alternativamente `pg_dump` manual sobre la URL externa).
- **Imágenes:** residen en Cloudinary (respaldo gestionado por el proveedor).
- **Configuración:** mantener un registro seguro de las variables de entorno fuera del repositorio (nunca versionar `.env`).

### 6. Monitoreo
- **Logs de aplicación:** disponibles en el panel de Render (errores de arranque, peticiones, fallos de envío de correo registrados por el `EmailService`).
- **SendGrid → Activity / Email Logs:** estado de entrega de cada correo (Processed / Delivered / Bounce).
- **Salud de la API:** la documentación `/docs` y las rutas públicas sirven como verificación rápida de disponibilidad.
- **Circuit Breaker de OSRM:** el backend degrada con elegancia hacia un cálculo aproximado (Haversine) cuando OSRM no responde.

### 7. Resolución de Problemas (Troubleshooting)

| Síntoma | Causa probable | Solución |
|---|---|---|
| La API no arranca (`ValidationError: Field required`) | Faltan variables de entorno obligatorias (p. ej. `SENDGRID_API_KEY`) | Definir todas las variables en el panel de Render. |
| Error al consultar usuarios tras un despliegue | Falta una columna nueva en una tabla existente | Ejecutar el script de migración idempotente correspondiente. |
| Los correos no llegan | Remitente no verificado / dominio sin autenticar / filtro institucional | Verificar el Single Sender o autenticar dominio en SendGrid; revisar carpeta de spam. |
| Primer request lento | Arranque en frío del plan *free* de Render | Esperar el arranque o subir de plan. |
| Rutas/tiempos incorrectos o ausentes | OSRM público saturado o caído | El Circuit Breaker activa el cálculo aproximado; reintentar más tarde. |

---

# 4.2.6 Mantenimiento

## 4.2.6.1 Plan de Mantenimiento

El mantenimiento del sistema se organiza en cuatro tipos clásicos, con prácticas específicas ya implementadas en el proyecto.

### 1. Mantenimiento Correctivo (corrección de errores)
- **Pruebas automatizadas como red de seguridad:**
  - *Backend:* suite con **pytest** en `tests/`, que cubre endpoints de autenticación, administración, propiedades, recomendación, workplaces y preferencias (`test_endpoints_*.py`), además de la lógica núcleo y utilitaria de recomendación (`test_recommend_core.py`, `test_recommend_utils.py`) y geocodificación (`test_geocode.py`).
  - *Móvil:* **126 pruebas** (8 suites) con `jest-expo` y `@testing-library/react-native`, incluyendo el componente `OtpInput`, los servicios de autenticación/correo, la API de recomendaciones, el servicio de rutas y los mappers de datos. Se ejecutan con `npm test`.
- **Flujo de corrección:** reproducir el error → escribir/ajustar una prueba que lo evidencie → corregir → verificar que toda la suite pase (`pytest` / `npm test`).
- **Logs centralizados** en Render y SendGrid para diagnóstico en producción.

### 2. Mantenimiento Adaptativo (cambios del entorno)
- **Gestión de dependencias con versiones fijadas** (`requirements.txt` y `package.json`) para builds reproducibles.
- **Capacidad de sustituir proveedores externos** demostrada con la migración de **Resend → SendGrid** sin afectar la lógica de negocio (servicio `EmailService` desacoplado).
- **Geocodificación con respaldo:** Nominatim como primario y Photon como *fallback* automático.
- **Compatibilidad de plataforma:** el móvil usa Expo SDK 54 / React Native 0.81 con la New Architecture, facilitando actualizaciones de SDK.

### 3. Mantenimiento Perfectivo (mejoras y nuevas funcionalidades)
- **Arquitecturas modulares** que aíslan el impacto de los cambios:
  - *Backend:* capas `api` (routers con la lógica de cada dominio), `core` (configuración, seguridad/JWT, conexión a BD, OTP y correo), `models` (SQLAlchemy) y `schemas` (Pydantic), con routers independientes (`auth`, `properties`, `recommend`, `workplaces`, `geocode`, `recommendation_preferences`, `admin`). *(La carpeta `app/services/` existe como reserva pero actualmente está vacía; la lógica de negocio reside en los routers.)*
  - *Móvil:* **Feature-Sliced Design** (`app` → `widgets` → `features` → `entities` → `shared`), con features como `auth`, `guest`, `recommendation`, `publish-housing`, `route-calculation` y `admin`.
- **Documentación viva:** `API_DOCS.md` (endpoints), `ARCHITECTURE_BACK.md` y `ARCHITECTURE_FRONT.md` (diagramas C4) actualizados con cada cambio relevante.
- **Reentrenamiento del modelo IA:** `ml_pipeline/train.py` regenera el modelo XGBoost; los artefactos resultantes (`ml_pipeline/model/xgboost_recommender.json` y `model_features.pkl`) se cargan una sola vez al iniciar la API desde `app/api/recommend.py`. La evaluación se realiza con `scripts/run_evaluation.py` y la construcción del dataset con `scripts/dataset_builder.py`.

### 4. Mantenimiento Preventivo (reducir fallos futuros)
- **Migraciones idempotentes** (`ADD COLUMN IF NOT EXISTS`) que evitan inconsistencias de esquema entre entornos.
- **Validación estricta de entrada** con Pydantic (backend) y TypeScript + rutas tipadas (móvil).
- **Manejo robusto de fallos externos:** Circuit Breaker sobre OSRM con degradación a Haversine; el `EmailService` captura excepciones y no interrumpe el flujo principal.
- **OTP persistente:** los códigos se guardan en PostgreSQL (`otp_codes`) con expiración y un solo uso, sobreviviendo a reinicios y a escalado horizontal.
- **Seguridad:** contraseñas con bcrypt, autenticación JWT, verificación de correo por OTP y rotación de credenciales recomendada (p. ej. ante exposición accidental).

### 5. Deuda Técnica y Mejoras Recomendadas
| Ítem | Acción recomendada |
|---|---|
| Adopción de un framework de migraciones | Evaluar **Alembic** para versionar el esquema de forma trazable en lugar de scripts manuales idempotentes. |
| Distribución móvil | Configurar **EAS Build** (`eas.json`, aún no presente) para generar binarios firmados y publicar en tiendas. |
| Servicios externos públicos (OSRM / Nominatim / Photon) | Evaluar instancias propias o un plan con SLA para producción a escala. |
| Plan *free* de Render | Considerar un plan de pago para evitar arranques en frío y ampliar la retención/respaldo de la base de datos. |
| Limpieza de OTP expirados | Programar una purga periódica de filas vencidas en `otp_codes` (los códigos vencidos se eliminan al consultarse, pero podrían acumularse si nunca se vuelven a consultar). |
| Carpeta `app/services/` vacía y `ml_pipeline/predictor.py` sin uso | Consolidar la lógica (mover negocio a `services/` o eliminar la carpeta) y centralizar la inferencia en `predictor.py`. |

> **Resueltos recientemente:** `render.yaml` ya usa `SENDGRID_*` + `USD_TO_PEN`; el almacén de OTP se migró de memoria a PostgreSQL (`otp_codes`).

### 6. Frecuencia Sugerida de Tareas
- **Continuo:** monitoreo de logs (Render) y entregabilidad de correos (SendGrid).
- **Por cada cambio:** ejecutar la suite de pruebas antes de hacer merge/deploy.
- **Mensual:** revisión de dependencias y parches de seguridad.
- **Periódico / según volumen:** respaldo de base de datos y reentrenamiento/evaluación del modelo de IA.
