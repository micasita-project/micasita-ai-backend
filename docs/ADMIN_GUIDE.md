# Guía Técnica del Administrador (Admin API) - MiCasita Backend

Este documento es una referencia técnica para el equipo de Frontend (React Native). Detalla exactamente qué enviar y qué recibir en cada uno de los endpoints destinados a la administración y moderación de la plataforma.

---

## 1. Autenticación (Login del Admin)

El administrador utiliza exactamente el mismo endpoint que un usuario normal. El backend es quien determina si el token devuelto posee permisos de administrador basándose en la base de datos.

### `POST /auth/login`
- **Headers:** `Content-Type: application/x-www-form-urlencoded`
- **Body (Form Data):**
  - `username` (string, requerido): Email del administrador (ej. `admin@micasita.ai`).
  - `password` (string, requerido): Contraseña.
- **Respuesta Exitosa (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
    "token_type": "bearer"
  }
  ```
- **Nota para el Front:** Debes guardar el `access_token` e inyectarlo en los headers de las siguientes peticiones como: `Authorization: Bearer <access_token>`.

---

## 2. Gestión de Viviendas (Moderación)

Todos estos endpoints requieren el Header: `Authorization: Bearer <access_token>` perteneciente a un admin.

### A. Obtener viviendas pendientes de revisión
Obtiene la lista de propiedades que acaban de ser publicadas o editadas y que tienen `status: "pending"`.

- **Endpoint:** `GET /admin/properties/pending?skip=0&limit=100`
- **Headers:** `Authorization: Bearer <token>`
- **Query Params (Opcionales):**
  - `skip` (integer): Paginación (default 0).
  - `limit` (integer): Cantidad por página (default 100).
- **Respuesta Exitosa (200 OK):**
  Devuelve un array de objetos `PropertyResponse`.
  ```json
  [
    {
      "id": 15,
      "publisher_id": 4,
      "title": "Hermoso depa en Miraflores",
      "property_type": "Departamento",
      "district": "Miraflores, Lima",
      "address": "Av. Pardo 123",
      "latitude": -12.1234,
      "longitude": -77.0234,
      "currency": "USD",
      "price": 1200.0,
      "total_area_sqm": 80.0,
      "covered_area_sqm": 80.0,
      "bedrooms": 2,
      "bathrooms": 2,
      "parking": 1,
      "antiquity": 5,
      "description": "Cerca a parques...",
      "images": ["url1", "url2"],
      "features": ["Gimnasio", "Piscina"],
      "source_url": null,
      "status": "pending"
    }
  ]
  ```

### B. Cambiar estado (Aprobar / Rechazar)
Usado para moderar una vivienda. Al rechazar una vivienda, se debe enviar **obligatoriamente** el motivo para que el usuario pueda corregirlo.

- **Endpoint:** `PATCH /admin/properties/{property_id}/status`
- **Headers:** 
  - `Authorization: Bearer <token>`
  - `Content-Type: application/json`
- **Body:**
  ```json
  {
    "status": "rejected",
    "rejection_reason": "Las fotos no son claras, por favor súbelas con mejor iluminación."
  }
  ```
  *(Nota: Los valores válidos para status son `"approved"` o `"rejected"`. Si es `"approved"`, el `rejection_reason` se ignora y se limpia en la base de datos. Si es `"rejected"` y no envías el motivo, el servidor devolverá error 400).*
- **Respuesta Exitosa (200 OK):** Devuelve el objeto de la propiedad actualizado (ver estructura en A, ahora incluye `"rejection_reason"`).
- **Errores:** 
  - `404 Not Found`: Si el `property_id` no existe.
  - `400 Bad Request`: Si envías un estado no válido, o si rechazas la vivienda sin enviar el `rejection_reason`.

### C. Editar una vivienda directamente
Si el admin desea corregir un detalle (ej. un error ortográfico) sin tener que rechazarla.

- **Endpoint:** `PATCH /properties/{property_id}`
- **Headers:** 
  - `Authorization: Bearer <token>`
  - `Content-Type: application/json`
- **Body:** Puedes enviar cualquier campo que desees actualizar de la propiedad. Todos son opcionales.
  ```json
  {
    "price": 1100.0,
    "title": "Título corregido por admin"
  }
  ```
- **Respuesta Exitosa (200 OK):** Devuelve la propiedad actualizada.
- **Comportamiento Backend:** Si la petición la hace un admin, el `status` de la vivienda **NO** se reinicia a `pending`, se mantiene como estaba.

### D. Eliminar una vivienda
- **Endpoint:** `DELETE /properties/{property_id}`
- **Headers:** `Authorization: Bearer <token>`
- **Respuesta Exitosa (204 No Content):** No devuelve body, solo código de estado HTTP 204.
- **Errores:** `404 Not Found`.

---

## 3. Gestión de Usuarios

Todos estos endpoints requieren el Header: `Authorization: Bearer <access_token>` perteneciente a un admin.

### A. Listar todos los usuarios
Obtiene un listado completo de los usuarios registrados en la plataforma.

- **Endpoint:** `GET /admin/users?skip=0&limit=100&search=...`
- **Headers:** `Authorization: Bearer <token>`
- **Query Params (Opcionales):**
  - `skip` (integer): Paginación (default 0).
  - `limit` (integer): Cantidad por página (default 100).
  - `search` (string): Texto para buscar por email, nombre o apellido (ej. `?search=juan`).
- **Respuesta Exitosa (200 OK):**

  Devuelve un array de objetos `UserResponse`.
  ```json
  [
    {
      "id": 1,
      "email": "user@example.com",
      "role": "user",
      "is_active": true,
      "name": "Juan",
      "last_name": "Pérez",
      "home_lat": -12.1234,
      "home_lon": -77.0234,
      "home_address": "Av. Pardo 123"
    }
  ]
  ```

### B. Bloquear o Suspender a un Usuario
Cambia el estado de acceso de un usuario. Si `is_active` es `false`, el usuario no podrá iniciar sesión (se le devolverá un error 403).

- **Endpoint:** `PATCH /admin/users/{user_id}/status`
- **Headers:** 
  - `Authorization: Bearer <token>`
  - `Content-Type: application/json`
- **Body:**
  ```json
  {
    "is_active": false
  }
  ```
- **Respuesta Exitosa (200 OK):** Devuelve el objeto del usuario actualizado.
- **Errores:**
  - `404 Not Found`: Si el `user_id` no existe.
  - `400 Bad Request`: Si el admin intenta bloquearse a sí mismo.

---

## 4. Notas Adicionales

- **Simulación de Correos:** Al aprobar o rechazar una vivienda usando `PATCH /admin/properties/{property_id}/status`, el backend actualmente simula el envío de un correo electrónico notificando al propietario. Esta acción se registra en la consola del servidor.
