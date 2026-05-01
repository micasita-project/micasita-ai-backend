# MiCasita AI Backend

Este es el backend principal del proyecto **MiCasita AI**, construido con **FastAPI** y **PostgreSQL**. Contiene la lógica de negocio, la conexión con la base de datos, las rutas de la API y la integración con los modelos de Machine Learning.

---

## 🚀 Cómo Iniciar el Proyecto (Local)

Sigue estos pasos para levantar el entorno de desarrollo en tu máquina local. Se incluyen comandos tanto para **macOS/Linux** como para **Windows (PowerShell)**.

### 1. Requisitos Previos
Asegúrate de tener instalado Python 3.11 (recomendado para evitar problemas de compilación con algunas librerías) y PostgreSQL.

**🍎 macOS (usando Homebrew):**
```bash
brew install python@3.11
brew install postgresql@18
```

**🪟 Windows:**
Descarga los instaladores desde sus páginas oficiales e instálalos:
- [Python 3.11](https://www.python.org/downloads/windows/)
- [PostgreSQL](https://www.postgresql.org/download/windows/)

### 2. Entorno Virtual y Dependencias
Crea un entorno virtual aislado (`venv`) e instala los paquetes:

**🍎 macOS / Linux:**
```bash
# 1. Crear el entorno virtual
python3.11 -m venv venv

# 2. Activar el entorno virtual
source venv/bin/activate

# 3. Instalar las dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

**🪟 Windows (PowerShell):**
```powershell
# 1. Crear el entorno virtual
py -3.11 -m venv venv

# 2. Activar el entorno virtual
.\venv\Scripts\Activate.ps1

# 3. Instalar las dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Base de Datos PostgreSQL
Asegúrate de que el servicio de PostgreSQL esté corriendo:

**🍎 macOS:**
```bash
brew services start postgresql@18
```

**🪟 Windows (PowerShell):**
Si instalaste PostgreSQL como servicio, normalmente se ejecuta automáticamente. Puedes comprobarlo o iniciarlo con:
```powershell
Start-Service -Name "postgresql-x64-15" # O la versión instalada
```
*(Nota: El proyecto está configurado para buscar un usuario `postgres` con contraseña `postgres` y una base de datos local llamada `micasita_db`).*

### 4. Poblar la Base de Datos (Seeding)
Antes de iniciar la API, puedes cargar el usuario por defecto y los datos de las propiedades corriendo el script de inicialización:

**🍎 macOS / Linux:**
```bash
export PYTHONPATH=.
python scripts/seed_db.py
```

**🪟 Windows (PowerShell):**
```powershell
$env:PYTHONPATH="."
python scripts/seed_db.py
```
*Esto creará el usuario `admin@micasita.ai` (password: `password123`) y cargará las propiedades desde el archivo JSON (omitiéndolo de forma segura si ya existen datos).*

### 5. Iniciar la API
Levanta el servidor local de desarrollo con recarga automática (Este comando es igual para todos los sistemas):
```bash
uvicorn app.main:app --reload
```
¡Listo! La API estará corriendo en `http://127.0.0.1:8000`.

---

## 📂 Arquitectura y Capas del Proyecto

El código está estructurado de forma modular y escalable. A continuación, te explico la responsabilidad de cada directorio:

### `/app`
Es el núcleo de la aplicación web (FastAPI). Está dividido en varias capas lógicas:
* **`/api` (Controladores/Rutas):** Define todos los endpoints (URLs) de la aplicación. Aquí se reciben las peticiones HTTP, pero no se procesa lógica compleja; simplemente se delega a la capa de servicios.
* **`/core` (Configuración):** Contiene variables de entorno, la conexión a la base de datos (`database.py`) y toda la lógica central de seguridad y autenticación mediante JWT (`security.py`).
* **`/models` (Modelos de Base de Datos):** Define las tablas de PostgreSQL usando SQLAlchemy (ej. `User`, `Property`, `Workplace`). Representa cómo se guardan físicamente los datos.
* **`/schemas` (Esquemas Pydantic):** Define cómo deben verse los datos que entran y salen de la API (DTOs). Se encargan de la validación de la información (ej. asegurar que un email sea válido antes de que llegue a la base de datos).
* **`/services` (Lógica de Negocio):** Aquí vive el "cerebro" de la app. Contiene funciones que procesan datos, integran los modelos de Machine Learning o aplican reglas de negocio antes de guardarlas en la base de datos.

### `/data`
Contiene los datasets en crudo (`/raw`) o procesados que usa la aplicación y los scripts de inicialización, como por ejemplo `housing.json` con toda la información de las propiedades.

### `/ml_pipeline`
Contiene toda la lógica relacionada a los modelos de Inteligencia Artificial y Machine Learning. Aquí se encuentran los scripts de entrenamiento, procesamiento de características y pipelines de predicción.

### `/scripts`
Scripts utilitarios que se corren por consola. Por ejemplo, `seed_db.py` para llenar la base de datos de prueba o generar documentación de manera automatizada.

---

## 📖 Documentación de la API
La documentación exhaustiva y detallada de cada endpoint de este proyecto (incluyendo requerimientos de Auth, Request Body y Responses) se encuentra autogenerada en el archivo [**API_DOCS.md**](./API_DOCS.md) ubicado en la raíz.
