# Documentación de la API — MiCasita AI

Base URL local: `http://localhost:8000`  
Documentación interactiva (Swagger): `http://localhost:8000/docs`

Todos los endpoints protegidos requieren el header:
```
Authorization: Bearer <access_token>
```

---

## Índice

- [Autenticación (`/auth`)](#autenticación-auth)
- [Viviendas (`/properties`)](#viviendas-properties)
- [Favoritos (`/properties/{id}/favorite`)](#favoritos)
- [Lugares de Trabajo (`/workplaces`)](#lugares-de-trabajo-workplaces)
- [Preferencias de Recomendación (`/recommendation_preferences`)](#preferencias-de-recomendación)
- [IA — Recomendaciones (`/recommend`)](#ia--recomendaciones-recommend)
- [Geocodificación (`/geocode`)](#geocodificación-geocode)
- [Administración (`/admin`)](#administración-admin)
- [Esquemas de datos](#esquemas-de-datos)

---

## Autenticación (`/auth`)

### `POST /auth/register`

Registra un nuevo usuario en el sistema. El rol asignado por defecto es `user`.

**Requiere autenticación:** No

**Request Body** (`application/json`):

| Campo       | Tipo     | Requerido | Descripción              |
| ----------- | -------- | --------- | ------------------------ |
| `email`     | `string` | Sí        | Email único del usuario  |
| `password`  | `string` | Sí        | Contraseña en texto plano (se hashea con bcrypt) |
| `name`      | `string` | No        | Nombre                   |
| `last_name` | `string` | No        | Apellido                 |

**Ejemplo de request:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "mi_contraseña_segura",
  "name": "Juan",
  "last_name": "Pérez"
}
```

**Respuestas:**

| Código | Descripción                                      |
| ------ | ------------------------------------------------ |
| `200`  | Usuario creado. Devuelve `UserResponse`          |
| `400`  | El email ya está registrado                      |
| `422`  | Error de validación (campo faltante o mal formato) |

---

### `POST /auth/login`

Autentica al usuario y devuelve un token JWT Bearer.

**Requiere autenticación:** No

**Request Body** (`application/x-www-form-urlencoded`):

| Campo      | Tipo     | Requerido | Descripción                        |
| ---------- | -------- | --------- | ---------------------------------- |
| `username` | `string` | Sí        | Email del usuario (campo `username` por OAuth2) |
| `password` | `string` | Sí        | Contraseña                         |

**Ejemplo de request:**
```
username=usuario@ejemplo.com&password=mi_contraseña_segura
```

**Respuesta exitosa (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Respuestas:**

| Código | Descripción                                        |
| ------ | -------------------------------------------------- |
| `200`  | Login exitoso. Devuelve `Token`                    |
| `401`  | Email o contraseña incorrectos                     |
| `403`  | Cuenta bloqueada o suspendida por un administrador |
| `422`  | Error de validación                                |

---

### `GET /auth/me`

Devuelve el perfil completo del usuario autenticado.

**Requiere autenticación:** Sí

**Respuesta exitosa (200):** Devuelve `UserResponse`

```json
{
  "id": 5,
  "email": "usuario@ejemplo.com",
  "role": "user",
  "is_active": true,
  "name": "Juan",
  "last_name": "Pérez",
  "home_lat": -12.0464,
  "home_lon": -77.0428,
  "home_address": "Av. Arequipa 1234, Miraflores"
}
```

**Respuestas:**

| Código | Descripción                  |
| ------ | ---------------------------- |
| `200`  | Perfil del usuario           |
| `401`  | Token inválido o expirado    |

---

### `PATCH /auth/me`

Actualiza el nombre y/o apellido del usuario autenticado. Solo los campos enviados se modifican.

**Requiere autenticación:** Sí

**Request Body** (`application/json`):

| Campo       | Tipo     | Requerido | Descripción  |
| ----------- | -------- | --------- | ------------ |
| `name`      | `string` | No        | Nuevo nombre |
| `last_name` | `string` | No        | Nuevo apellido |

**Ejemplo de request:**
```json
{
  "name": "Carlos"
}
```

**Respuestas:**

| Código | Descripción                         |
| ------ | ----------------------------------- |
| `200`  | Perfil actualizado. Devuelve `UserResponse` |
| `401`  | Token inválido o expirado           |
| `422`  | Error de validación                 |

---

### `PUT /auth/me/home`

Actualiza la ubicación de la vivienda actual del usuario. Esta coordenada se usa para calcular el ahorro de tiempo en las recomendaciones.

**Requiere autenticación:** Sí

**Request Body** (`application/json`):

| Campo          | Tipo     | Requerido | Descripción                           |
| -------------- | -------- | --------- | ------------------------------------- |
| `home_lat`     | `number` | Sí        | Latitud de la vivienda actual         |
| `home_lon`     | `number` | Sí        | Longitud de la vivienda actual        |
| `home_address` | `string` | Sí        | Dirección legible (para mostrar en UI) |

**Ejemplo de request:**
```json
{
  "home_lat": -12.1167,
  "home_lon": -77.0306,
  "home_address": "Av. Universitaria 1801, San Miguel, Lima"
}
```

**Respuestas:**

| Código | Descripción                             |
| ------ | --------------------------------------- |
| `200`  | Ubicación actualizada. Devuelve `UserResponse`  |
| `400`  | Coordenadas fuera de Lima Metropolitana         |
| `401`  | Token inválido o expirado                       |
| `422`  | Error de validación                             |

---

## Viviendas (`/properties`)

### `POST /properties/upload_image`

Sube una imagen al contenedor de Azure Blob Storage aplicando compresión automática. Devuelve la URL pública permanente para incluir en `PropertyCreate`.

**Requiere autenticación:** Sí

**Request Body** (`multipart/form-data`):

| Campo  | Tipo   | Requerido | Descripción                         |
| ------ | ------ | --------- | ----------------------------------- |
| `file` | `file` | Sí        | Imagen (jpg, png, webp, etc.)       |

**Respuesta exitosa (200):**
```json
{
  "url": "https://micasitastorage.blob.core.windows.net/images/3f7a8b2c-....jpg"
}
```

**Respuestas:**

| Código | Descripción                                      |
| ------ | ------------------------------------------------ |
| `200`  | URL pública de la imagen subida                  |
| `400`  | Error al subir a Azure (formato inválido, etc.)  |
| `401`  | Token inválido o expirado                        |
| `500`  | Azure no configurado en el servidor              |

---

### `POST /properties/`

Crea una nueva publicación de vivienda. El estado inicial siempre es `pending` (en revisión por un administrador).

**Requiere autenticación:** Sí

**Request Body** (`application/json`) — esquema `PropertyCreate`:

| Campo               | Tipo             | Requerido | Descripción                                       |
| ------------------- | ---------------- | --------- | ------------------------------------------------- |
| `title`             | `string`         | Sí        | Título de la publicación                          |
| `property_type`     | `string`         | Sí        | Tipo: `"casa"`, `"departamento"`, etc.            |
| `district`          | `string`         | Sí        | Distrito de Lima                                  |
| `address`           | `string`         | Sí        | Dirección completa                                |
| `latitude`          | `number`         | Sí        | Latitud (WGS84)                                   |
| `longitude`         | `number`         | Sí        | Longitud (WGS84)                                  |
| `currency`          | `string`         | No        | `"PEN"` o `"USD"`                                 |
| `price`             | `number`         | No        | Precio de alquiler mensual                        |
| `total_area_sqm`    | `number`         | Sí        | Área total en m²                                  |
| `covered_area_sqm`  | `number`         | No        | Área techada en m²                                |
| `bedrooms`          | `integer`        | No        | Número de habitaciones                            |
| `bathrooms`         | `integer`        | No        | Número de baños                                   |
| `parking`           | `integer`        | No        | Número de estacionamientos                        |
| `antiquity`         | `integer`        | No        | Antigüedad en años                                |
| `description`       | `string`         | No        | Descripción detallada                             |
| `images`            | `array[string]`  | No        | Lista de URLs de imágenes (subidas con `/upload_image`) |
| `features`          | `array[string]`  | No        | Características: `["Piscina", "Gym", "Amoblado"]` |
| `source_url`        | `string`         | No        | URL de origen si fue importada                    |

**Ejemplo de request:**
```json
{
  "title": "Departamento moderno en Miraflores",
  "property_type": "departamento",
  "district": "Miraflores",
  "address": "Calle Schell 345, Miraflores",
  "latitude": -18.1167,
  "longitude": -77.0306,
  "currency": "USD",
  "price": 800.0,
  "total_area_sqm": 75.0,
  "bedrooms": 2,
  "bathrooms": 1,
  "images": ["https://...blob.core.windows.net/images/abc.jpg"],
  "features": ["Amoblado", "Balcón"]
}
```

**Respuestas:**

| Código | Descripción                                          |
| ------ | ---------------------------------------------------- |
| `200`  | Vivienda creada en estado `pending`. Devuelve `PropertyResponse` |
| `401`  | Token inválido o expirado                            |
| `422`  | Error de validación                                  |

---

### `GET /properties/`

Lista las viviendas **aprobadas** (`status=approved`) con paginación y filtros opcionales. No muestra viviendas de usuarios bloqueados.

**Requiere autenticación:** No (si se envía token, marca favoritos del usuario en la respuesta)

**Parámetros de query:**

| Nombre         | Tipo      | Default | Descripción                              |
| -------------- | --------- | ------- | ---------------------------------------- |
| `skip`         | `integer` | `0`     | Registros a saltar (para paginación)     |
| `limit`        | `integer` | `10`    | Máximo de resultados por página          |
| `district`     | `string`  | —       | Filtrar por distrito (búsqueda parcial, case-insensitive) |
| `bedrooms`     | `integer` | —       | Mínimo de habitaciones                   |
| `bathrooms`    | `integer` | —       | Mínimo de baños                          |
| `parking`      | `integer` | —       | Mínimo de estacionamientos               |
| `min_area_sqm` | `number`  | —       | Área total mínima en m²                  |
| `min_price`    | `number`  | —       | Precio mínimo de alquiler                |
| `max_price`    | `number`  | —       | Precio máximo de alquiler                |

**Respuesta exitosa (200):** Devuelve `PaginatedPropertyResponse`

```json
{
  "total": 1020,
  "items": [
    {
      "id": 42,
      "title": "Hermosa casa en San Borja",
      "property_type": "casa",
      "district": "San Borja",
      "address": "Av. San Luis 2180",
      "latitude": -12.0931,
      "longitude": -77.0010,
      "currency": "USD",
      "price": 1200.0,
      "total_area_sqm": 150.0,
      "bedrooms": 3,
      "bathrooms": 2,
      "status": "approved",
      "is_favorite": false,
      "images": ["https://..."]
    }
  ]
}
```

**Respuestas:**

| Código | Descripción                          |
| ------ | ------------------------------------ |
| `200`  | Lista paginada de viviendas          |
| `422`  | Parámetros de query inválidos        |

---

### `GET /properties/mine`

Devuelve todas las viviendas publicadas por el usuario autenticado, en cualquier estado (`pending`, `approved`, `rejected`).

**Requiere autenticación:** Sí

**Respuesta exitosa (200):** Lista de `PropertyResponse`

**Respuestas:**

| Código | Descripción                                          |
| ------ | ---------------------------------------------------- |
| `200`  | Lista de viviendas del usuario                       |
| `401`  | Token inválido o expirado                            |

---

### `GET /properties/favorites`

Devuelve la lista de viviendas marcadas como favoritas por el usuario autenticado.

**Requiere autenticación:** Sí

**Respuesta exitosa (200):** Lista de `PropertyResponse` (todos con `is_favorite: true`)

**Respuestas:**

| Código | Descripción                           |
| ------ | ------------------------------------- |
| `200`  | Lista de viviendas favoritas          |
| `401`  | Token inválido o expirado             |

---

### `GET /properties/{property_id}`

Obtiene el detalle completo de una vivienda por su ID. Si el usuario está autenticado, incluye el campo `is_favorite`.

**Requiere autenticación:** No

**Parámetros de path:**

| Nombre        | Tipo      | Descripción     |
| ------------- | --------- | --------------- |
| `property_id` | `integer` | ID de la vivienda |

**Respuesta exitosa (200):** Devuelve `PropertyResponse`

**Respuestas:**

| Código | Descripción                  |
| ------ | ---------------------------- |
| `200`  | Detalle de la vivienda       |
| `404`  | Vivienda no encontrada       |
| `422`  | ID inválido                  |

---

### `PATCH /properties/{property_id}`

Actualiza los campos de una vivienda. Solo el dueño o un admin pueden editar. No se puede editar si el estado es `pending`. Al editar (sin ser admin), la vivienda vuelve automáticamente a estado `pending`.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre        | Tipo      | Descripción       |
| ------------- | --------- | ----------------- |
| `property_id` | `integer` | ID de la vivienda |

**Request Body** (`application/json`) — esquema `PropertyUpdate` (todos los campos opcionales, igual que `PropertyCreate`).

**Respuestas:**

| Código | Descripción                                                        |
| ------ | ------------------------------------------------------------------ |
| `200`  | Vivienda actualizada. Devuelve `PropertyResponse`                  |
| `403`  | Sin permisos o vivienda en estado `pending` (no se puede editar)   |
| `404`  | Vivienda no encontrada                                             |
| `422`  | Error de validación                                                |

---

### `DELETE /properties/{property_id}`

Elimina permanentemente una vivienda. Solo el dueño o un admin pueden hacerlo.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre        | Tipo      | Descripción       |
| ------------- | --------- | ----------------- |
| `property_id` | `integer` | ID de la vivienda |

**Respuestas:**

| Código | Descripción                              |
| ------ | ---------------------------------------- |
| `204`  | Eliminada correctamente (sin contenido)  |
| `403`  | Sin permisos                             |
| `404`  | Vivienda no encontrada                   |
| `422`  | ID inválido                              |

---

## Favoritos

### `POST /properties/{property_id}/favorite`

Añade una vivienda a la lista de favoritos del usuario. Si ya estaba marcada, devuelve un mensaje sin error.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre        | Tipo      | Descripción       |
| ------------- | --------- | ----------------- |
| `property_id` | `integer` | ID de la vivienda |

**Respuesta exitosa (201):**
```json
{ "message": "Añadida a favoritos exitosamente" }
```

**Respuestas:**

| Código | Descripción                     |
| ------ | ------------------------------- |
| `201`  | Añadida a favoritos             |
| `200`  | Ya estaba en favoritos          |
| `401`  | Token inválido o expirado       |
| `404`  | Vivienda no encontrada          |

---

### `DELETE /properties/{property_id}/favorite`

Quita una vivienda de la lista de favoritos del usuario.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre        | Tipo      | Descripción       |
| ------------- | --------- | ----------------- |
| `property_id` | `integer` | ID de la vivienda |

**Respuesta exitosa (200):**
```json
{ "message": "Quitada de favoritos exitosamente" }
```

**Respuestas:**

| Código | Descripción                          |
| ------ | ------------------------------------ |
| `200`  | Quitada de favoritos                 |
| `401`  | Token inválido o expirado            |
| `404`  | La vivienda no estaba en favoritos   |

---

## Lugares de Trabajo (`/workplaces`)

### `POST /workplaces/`

Registra un nuevo lugar de trabajo o estudio. Las coordenadas se usan como punto de origen para el motor de recomendaciones.

**Requiere autenticación:** Sí

**Request Body** (`application/json`):

| Campo          | Tipo     | Requerido | Descripción                              |
| -------------- | -------- | --------- | ---------------------------------------- |
| `work_address` | `string` | Sí        | Dirección legible del lugar de trabajo                       |
| `work_lat`     | `number` | Sí        | Latitud (debe estar dentro de Lima Metropolitana)            |
| `work_lon`     | `number` | Sí        | Longitud (debe estar dentro de Lima Metropolitana)           |

**Ejemplo de request:**
```json
{
  "work_address": "Av. Javier Prado Este 4600, San Borja",
  "work_lat": -12.0931,
  "work_lon": -77.0010
}
```

**Respuesta exitosa (200):** Devuelve `WorkplaceResponse`

**Respuestas:**

| Código | Descripción                                    |
| ------ | ---------------------------------------------- |
| `200`  | Workplace creado. Devuelve `WorkplaceResponse`                              |
| `400`  | Coordenadas fuera de Lima Metropolitana                                     |
| `401`  | Token inválido o expirado                                                   |
| `422`  | Error de validación                                                         |

---

### `GET /workplaces/`

Lista todos los lugares de trabajo guardados por el usuario autenticado.

**Requiere autenticación:** Sí

**Respuesta exitosa (200):** Lista de `WorkplaceResponse`

**Respuestas:**

| Código | Descripción                           |
| ------ | ------------------------------------- |
| `200`  | Lista de lugares de trabajo           |
| `401`  | Token inválido o expirado             |

---

### `PATCH /workplaces/{workplace_id}`

Actualiza los datos de un lugar de trabajo. Solo se modifican los campos enviados.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre         | Tipo      | Descripción            |
| -------------- | --------- | ---------------------- |
| `workplace_id` | `integer` | ID del lugar de trabajo |

**Request Body** (`application/json`) — todos los campos son opcionales:

| Campo          | Tipo     | Descripción                            |
| -------------- | -------- | -------------------------------------- |
| `work_address` | `string` | Nueva dirección                        |
| `work_lat`     | `number` | Nueva latitud                          |
| `work_lon`     | `number` | Nueva longitud                         |

**Respuestas:**

| Código | Descripción                                    |
| ------ | ---------------------------------------------- |
| `200`  | Workplace actualizado. Devuelve `WorkplaceResponse`  |
| `400`  | Coordenadas fuera de Lima Metropolitana              |
| `401`  | Token inválido o expirado                            |
| `404`  | Workplace no encontrado                              |
| `422`  | Error de validación                                  |

---

### `DELETE /workplaces/{workplace_id}`

Elimina un lugar de trabajo. Solo el dueño puede eliminarlo.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre         | Tipo      | Descripción            |
| -------------- | --------- | ---------------------- |
| `workplace_id` | `integer` | ID del lugar de trabajo |

**Respuestas:**

| Código | Descripción                           |
| ------ | ------------------------------------- |
| `204`  | Eliminado correctamente               |
| `401`  | Token inválido o expirado             |
| `404`  | Workplace no encontrado               |

---

## Preferencias de Recomendación

Cada workplace puede tener una única configuración de preferencias que el motor de IA usa para personalizar las recomendaciones.

### `POST /recommendation_preferences/`

Crea las preferencias de recomendación asociadas a un workplace. Solo se puede crear una vez por workplace; para modificarlas, usar `PATCH`.

**Requiere autenticación:** Sí

**Request Body** (`application/json`):

| Campo                    | Tipo     | Requerido | Descripción                                              |
| ------------------------ | -------- | --------- | -------------------------------------------------------- |
| `workplace_id`           | `integer`| Sí        | ID del workplace al que pertenecen las preferencias      |
| `budget`                 | `number` | Sí        | Presupuesto máximo de alquiler mensual (en la moneda del país) |
| `preferred_transportation`| `string`| Sí        | Medio de transporte: `"driving"`, `"cycling"`, `"walking"` |
| `max_distance_km`        | `number` | No        | Radio máximo de búsqueda en km (default: 10, rango: 1–50) |

**Ejemplo de request:**
```json
{
  "workplace_id": 3,
  "budget": 1500.0,
  "preferred_transportation": "driving",
  "max_distance_km": 15.0
}
```

**Respuesta exitosa (200):** Devuelve `RecommendationPreferenceResponse`

**Respuestas:**

| Código | Descripción                                              |
| ------ | -------------------------------------------------------- |
| `200`  | Preferencias creadas                                     |
| `400`  | Ya existen preferencias para este workplace (usar PATCH) |
| `401`  | Token inválido o expirado                                |
| `404`  | Workplace no encontrado o no pertenece al usuario        |
| `422`  | Error de validación (ej. `max_distance_km` fuera de rango) |

---

### `GET /recommendation_preferences/`

Devuelve las preferencias del usuario. Se puede filtrar por workplace.

**Requiere autenticación:** Sí

**Parámetros de query:**

| Nombre         | Tipo      | Requerido | Descripción                              |
| -------------- | --------- | --------- | ---------------------------------------- |
| `workplace_id` | `integer` | No        | Filtrar por ID de workplace específico   |

**Respuesta exitosa (200):** Lista de `RecommendationPreferenceResponse`

**Respuestas:**

| Código | Descripción                             |
| ------ | --------------------------------------- |
| `200`  | Lista de preferencias del usuario       |
| `401`  | Token inválido o expirado               |

---

### `PATCH /recommendation_preferences/{pref_id}`

Actualiza las preferencias de recomendación. Solo se modifican los campos enviados.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre    | Tipo      | Descripción              |
| --------- | --------- | ------------------------ |
| `pref_id` | `integer` | ID de las preferencias   |

**Request Body** (`application/json`) — todos los campos son opcionales:

| Campo                     | Tipo     | Descripción                                              |
| ------------------------- | -------- | -------------------------------------------------------- |
| `budget`                  | `number` | Nuevo presupuesto                                        |
| `preferred_transportation`| `string` | Nuevo medio de transporte                                |
| `max_distance_km`         | `number` | Nuevo radio máximo (rango: 1–50)                         |

**Respuestas:**

| Código | Descripción                                           |
| ------ | ----------------------------------------------------- |
| `200`  | Preferencias actualizadas. Devuelve `RecommendationPreferenceResponse` |
| `401`  | Token inválido o expirado                             |
| `404`  | Preferencias no encontradas                           |
| `422`  | Error de validación                                   |

---

## IA — Recomendaciones (`/recommend`)

El motor de IA usa un modelo XGBoost entrenado con datos de Lima. Calcula el tiempo de viaje al trabajo usando OSRM (rutas reales). Si OSRM falla o supera 5 timeouts consecutivos, activa un circuit breaker y usa Haversine + velocidades promedio como fallback.

### `POST /recommend/guest`

Genera recomendaciones sin necesidad de cuenta. Requiere pasar todos los parámetros manualmente.

**Requiere autenticación:** No (si se envía token, marca favoritos en la respuesta)

**Request Body** (`application/json`):

| Campo                      | Tipo     | Requerido | Descripción                                              |
| -------------------------- | -------- | --------- | -------------------------------------------------------- |
| `work_lat`                 | `number` | Sí        | Latitud del lugar de trabajo (debe estar en Lima)        |
| `work_lon`                 | `number` | Sí        | Longitud del lugar de trabajo                            |
| `budget`                   | `number` | Sí        | Presupuesto máximo en **soles (PEN)**                    |
| `preferred_transportation` | `string` | Sí        | `"driving"`, `"cycling"` o `"walking"`                   |
| `max_distance_km`          | `number` | No        | Radio máximo en km (default: 10)                         |
| `home_lat`                 | `number` | No        | Latitud de la casa actual (para calcular tiempo ahorrado)|
| `home_lon`                 | `number` | No        | Longitud de la casa actual                               |

**Ejemplo de request:**
```json
{
  "work_lat": -12.0931,
  "work_lon": -77.0010,
  "budget": 1200.0,
  "preferred_transportation": "driving",
  "max_distance_km": 12.0,
  "home_lat": -12.1500,
  "home_lon": -77.0200
}
```

**Respuesta exitosa (200):** `RecommendationPageResponse`

```json
{
  "results": [
    {
      "property": { "id": 42, "title": "Casa en San Borja", ... },
      "match_score": 87.4,
      "predicted_time_min": 18,
      "time_saved_mins": 12
    }
  ],
  "total": 1,
  "message": null,
  "min_price_in_area": null
}
```

> Cuando el presupuesto es insuficiente para la zona, `results` estará vacío, `message` explicará el motivo y `min_price_in_area` mostrará el precio mínimo disponible en soles.

**Respuestas:**

| Código | Descripción                              |
| ------ | ---------------------------------------- |
| `200`  | Página de viviendas recomendadas         |
| `422`  | Error de validación                      |

---

### `POST /recommend/workplaces/{workplace_id}/generate`

Ejecuta el modelo XGBoost usando el workplace y las preferencias guardadas del usuario. **Guarda el resultado en el historial** (no sobrescribe, crea una nueva entrada). Recomendado para el flujo principal de la app.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre         | Tipo      | Descripción            |
| -------------- | --------- | ---------------------- |
| `workplace_id` | `integer` | ID del lugar de trabajo |

**Parámetros de query:**

| Nombre           | Tipo      | Default | Descripción                                              |
| ---------------- | --------- | ------- | -------------------------------------------------------- |
| `max_distance_km`| `number`  | `10.0`  | Sobreescribe el valor de preferencias si se envía        |

**Respuesta exitosa (200):** `RecommendationPageResponse`

**Respuestas:**

| Código | Descripción                                                  |
| ------ | ------------------------------------------------------------ |
| `200`  | Recomendaciones generadas y guardadas en historial           |
| `400`  | El workplace no tiene preferencias de recomendación          |
| `401`  | Token inválido o expirado                                    |
| `404`  | Workplace no encontrado                                      |

---

### `GET /recommend/workplaces/{workplace_id}/latest`

Devuelve la última recomendación generada **sin ejecutar la IA**. Actualiza el estado `is_favorite` en tiempo real aunque el caché sea antiguo.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre         | Tipo      | Descripción            |
| -------------- | --------- | ---------------------- |
| `workplace_id` | `integer` | ID del lugar de trabajo |

**Respuesta exitosa (200):** `RecommendationPageResponse` (del historial más reciente)

**Respuestas:**

| Código | Descripción                                               |
| ------ | --------------------------------------------------------- |
| `200`  | Última recomendación cacheada                             |
| `401`  | Token inválido o expirado                                 |
| `404`  | Workplace no encontrado o sin recomendaciones guardadas   |

---

### `GET /recommend/workplaces/{workplace_id}/history`

Devuelve el historial completo de todas las recomendaciones generadas para un workplace, ordenado del más reciente al más antiguo.

**Requiere autenticación:** Sí

**Parámetros de path:**

| Nombre         | Tipo      | Descripción            |
| -------------- | --------- | ---------------------- |
| `workplace_id` | `integer` | ID del lugar de trabajo |

**Respuesta exitosa (200):**
```json
[
  {
    "id": 10,
    "workplace_id": 3,
    "results": [...],
    "created_at": "2025-05-09T14:32:00"
  }
]
```

**Respuestas:**

| Código | Descripción                         |
| ------ | ----------------------------------- |
| `200`  | Historial de recomendaciones        |
| `401`  | Token inválido o expirado           |
| `404`  | Workplace no encontrado             |

---

### `GET /recommend/workplaces/{workplace_id}` *(deprecated)*

> **Obsoleto.** Ejecuta XGBoost directamente sin guardar en historial. Usar `POST /recommend/workplaces/{workplace_id}/generate` en su lugar.

**Requiere autenticación:** Sí

**Respuestas:**

| Código | Descripción                                  |
| ------ | -------------------------------------------- |
| `200`  | `RecommendationPageResponse` (no se guarda)  |
| `400`  | Sin preferencias configuradas                |
| `404`  | Workplace no encontrado                      |

---

## Geocodificación (`/geocode`)

Proxy hacia la API pública de Nominatim (OpenStreetMap), limitado a Lima metropolitana.

### `GET /geocode/search`

Autocompletado de direcciones. Útil para el campo de búsqueda en la app.

**Requiere autenticación:** No

**Parámetros de query:**

| Nombre  | Tipo      | Requerido | Default | Descripción                                |
| ------- | --------- | --------- | ------- | ------------------------------------------ |
| `q`     | `string`  | Sí        | —       | Texto de búsqueda (mínimo 3 caracteres)    |
| `limit` | `integer` | No        | `5`     | Máximo de sugerencias (1–10)               |

**Respuesta exitosa (200):** Lista de `GeocodeSuggestion`

```json
[
  {
    "display_name": "Av. Javier Prado Este, San Borja, Lima, Perú",
    "latitude": -12.0931,
    "longitude": -77.0010,
    "place_type": "road",
    "district": "San Borja"
  }
]
```

**Respuestas:**

| Código | Descripción                                    |
| ------ | ---------------------------------------------- |
| `200`  | Lista de sugerencias (vacía si Nominatim falla)|
| `422`  | Parámetro `q` faltante o con menos de 3 chars  |

---

### `GET /geocode/reverse`

Obtiene la dirección a partir de coordenadas geográficas (reverse geocoding).

**Requiere autenticación:** No

**Parámetros de query:**

| Nombre | Tipo     | Requerido | Descripción |
| ------ | -------- | --------- | ----------- |
| `lat`  | `number` | Sí        | Latitud     |
| `lon`  | `number` | Sí        | Longitud    |

**Respuesta exitosa (200):** Devuelve `GeocodeSuggestion`

```json
{
  "display_name": "Calle Schell 345, Miraflores, Lima, Perú",
  "latitude": -18.1167,
  "longitude": -77.0306,
  "place_type": "building",
  "district": "Miraflores"
}
```

**Respuestas:**

| Código | Descripción                                         |
| ------ | --------------------------------------------------- |
| `200`  | Dirección encontrada (o fallback genérico si falla) |
| `422`  | Parámetros `lat`/`lon` faltantes                    |

---

## Administración (`/admin`)

Todos los endpoints de esta sección requieren rol `admin`. Devuelven `403 Forbidden` si el usuario autenticado no es administrador.

### `GET /admin/properties/pending`

Lista todas las viviendas en estado `pending` esperando revisión.

**Requiere autenticación:** Sí (rol `admin`)

**Parámetros de query:**

| Nombre  | Tipo      | Default | Descripción            |
| ------- | --------- | ------- | ---------------------- |
| `skip`  | `integer` | `0`     | Registros a saltar     |
| `limit` | `integer` | `100`   | Máximo de resultados   |

**Respuesta exitosa (200):** Lista de `PropertyResponse`

**Respuestas:**

| Código | Descripción                         |
| ------ | ----------------------------------- |
| `200`  | Lista de viviendas pendientes       |
| `401`  | Token inválido o expirado           |
| `403`  | No es administrador                 |

---

### `PATCH /admin/properties/{property_id}/status`

Aprueba o rechaza una vivienda. Al rechazar, es obligatorio incluir el motivo. Se envía notificación por email al propietario.

**Requiere autenticación:** Sí (rol `admin`)

**Parámetros de path:**

| Nombre        | Tipo      | Descripción       |
| ------------- | --------- | ----------------- |
| `property_id` | `integer` | ID de la vivienda |

**Request Body** (`application/json`):

| Campo              | Tipo     | Requerido | Descripción                                              |
| ------------------ | -------- | --------- | -------------------------------------------------------- |
| `status`           | `string` | Sí        | `"approved"`, `"rejected"` o `"pending"`                |
| `rejection_reason` | `string` | Condicional | Obligatorio si `status` es `"rejected"`              |

**Ejemplo de request:**
```json
{
  "status": "rejected",
  "rejection_reason": "Las imágenes no corresponden a la propiedad descrita."
}
```

**Respuesta exitosa (200):** Devuelve `PropertyResponse` actualizado.

**Respuestas:**

| Código | Descripción                                              |
| ------ | -------------------------------------------------------- |
| `200`  | Estado actualizado. Email enviado al propietario         |
| `400`  | Estado inválido o `rejection_reason` faltante al rechazar |
| `401`  | Token inválido o expirado                                |
| `403`  | No es administrador                                      |
| `404`  | Vivienda no encontrada                                   |

---

### `GET /admin/users`

Lista todos los usuarios registrados con búsqueda opcional por email, nombre o apellido.

**Requiere autenticación:** Sí (rol `admin`)

**Parámetros de query:**

| Nombre   | Tipo      | Default | Descripción                                          |
| -------- | --------- | ------- | ---------------------------------------------------- |
| `search` | `string`  | —       | Búsqueda parcial por email, nombre o apellido        |
| `skip`   | `integer` | `0`     | Registros a saltar                                   |
| `limit`  | `integer` | `100`   | Máximo de resultados                                 |

**Respuesta exitosa (200):** Lista de `UserResponse`

**Respuestas:**

| Código | Descripción                     |
| ------ | ------------------------------- |
| `200`  | Lista de usuarios               |
| `401`  | Token inválido o expirado       |
| `403`  | No es administrador             |

---

### `PATCH /admin/users/{user_id}/status`

Activa o bloquea la cuenta de un usuario. Al bloquear, todas sus viviendas se ocultan automáticamente del feed público (`hidden_by_user_block=true`). Se envía notificación por email. Un admin no puede bloquearse a sí mismo.

**Requiere autenticación:** Sí (rol `admin`)

**Parámetros de path:**

| Nombre    | Tipo      | Descripción      |
| --------- | --------- | ---------------- |
| `user_id` | `integer` | ID del usuario   |

**Request Body** (`application/json`):

| Campo       | Tipo      | Requerido | Descripción                                 |
| ----------- | --------- | --------- | ------------------------------------------- |
| `is_active` | `boolean` | Sí        | `true` para activar, `false` para bloquear  |

**Ejemplo de request:**
```json
{ "is_active": false }
```

**Respuesta exitosa (200):** Devuelve `UserResponse` actualizado.

**Respuestas:**

| Código | Descripción                                              |
| ------ | -------------------------------------------------------- |
| `200`  | Estado actualizado. Email enviado al usuario             |
| `400`  | Un admin no puede bloquearse a sí mismo                  |
| `401`  | Token inválido o expirado                                |
| `403`  | No es administrador                                      |
| `404`  | Usuario no encontrado                                    |

---

## Esquemas de datos

### `UserResponse`
```json
{
  "id": 5,
  "email": "usuario@ejemplo.com",
  "role": "user",
  "is_active": true,
  "name": "Juan",
  "last_name": "Pérez",
  "home_lat": -12.0464,
  "home_lon": -77.0428,
  "home_address": "Av. Arequipa 1234, Miraflores"
}
```

### `PropertyResponse`
```json
{
  "id": 42,
  "publisher_id": 5,
  "title": "Departamento en Miraflores",
  "property_type": "departamento",
  "district": "Miraflores",
  "address": "Calle Schell 345",
  "latitude": -18.1167,
  "longitude": -77.0306,
  "currency": "USD",
  "price": 800.0,
  "total_area_sqm": 75.0,
  "covered_area_sqm": 60.0,
  "bedrooms": 2,
  "bathrooms": 1,
  "parking": 0,
  "antiquity": 5,
  "description": "Departamento moderno con vista al parque.",
  "images": ["https://...blob.core.windows.net/images/abc.jpg"],
  "features": ["Amoblado", "Balcón"],
  "source_url": null,
  "status": "approved",
  "rejection_reason": null,
  "is_favorite": false
}
```

### `WorkplaceResponse`
```json
{
  "id": 3,
  "user_id": 5,
  "work_address": "Av. Javier Prado Este 4600, San Borja",
  "work_lat": -12.0931,
  "work_lon": -77.0010
}
```

### `RecommendationPreferenceResponse`
```json
{
  "id": 1,
  "user_id": 5,
  "workplace_id": 3,
  "budget": 1500.0,
  "preferred_transportation": "driving",
  "max_distance_km": 15.0
}
```

### `RecommendationPageResponse`
```json
{
  "results": [ ...RecommendationResponse ],
  "total": 5,
  "message": null,
  "min_price_in_area": null
}
```

> `message` es non-null cuando no hay resultados: explica si el radio no tiene viviendas o si el presupuesto es insuficiente. `min_price_in_area` es non-null cuando hay viviendas en el radio pero ninguna entra en el presupuesto — muestra el precio mínimo disponible en **soles**.

### `RecommendationResponse`
```json
{
  "property": { ...PropertyResponse },
  "match_score": 87.4,
  "predicted_time_min": 18,
  "time_saved_mins": 12
}
```

### `GeocodeSuggestion`
```json
{
  "display_name": "Av. Javier Prado Este, San Borja, Lima, Perú",
  "latitude": -12.0931,
  "longitude": -77.0010,
  "place_type": "road",
  "district": "San Borja"
}
```

### `Token`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

*Documentación generada para MiCasita AI — Backend v1.0*
