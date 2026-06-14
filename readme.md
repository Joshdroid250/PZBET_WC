# ⚽ PZBET - FIFA World Cup Edition

PZBET es un bot de Discord avanzado para la gestión de apuestas deportivas tipo **Parimutuel** (pozo común), totalmente optimizado para la Copa del Mundo 2026 utilizando la API oficial de la FIFA.

## 🚀 Características Principales

- **API FIFA Integrada**: Conexión en tiempo real con marcadores, estados de partidos e IDs alfanuméricos oficiales.
- **Sistema Parimutuel**: Las cuotas se calculan dinámicamente basadas en el volumen total del pozo.
- **Rastreador de Goles en Vivo**: Actualización automática de marcadores en canales de anuncios con edición de mensajes en tiempo real.
- **Candado del Minuto 90**: Bloqueo automático de apuestas y cashouts al llegar al tiempo reglamentario para proteger la integridad del pozo.
- **Parlays (Combinadas)**: Soporte para apuestas múltiples con resolución automática.
- **Cashout**: Reembolso parcial (80%) para apuestas en partidos que aún no han terminado o llegado al minuto 90.
- **Administración Robusta**: Herramientas para limpieza de base de datos, resolución manual y gestión de usuarios.

## 🛠️ Instalación

1. Clona el repositorio.
2. Crea un entorno virtual y activa:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```
3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Configura tu archivo `.env` (ver sección de Configuración).
5. Inicia el bot:
   ```bash
   python bot.py
   ```

## ⚙️ Configuración (.env)

El bot requiere las siguientes variables de entorno:

```env
DISCORD_TOKEN=tu_token_aquí
BOT_PREFIX=!
ANNOUNCEMENT_CHANNEL_ID=id_del_canal_de_goles
COMPETITION_CODE=WC
FIFA_API_BASE_URL=https://fifaapi-v7l1.onrender.com/v4
```

## 📂 Estructura del Proyecto

- `bot.py`: Punto de entrada principal.
- `api_football.py`: Módulo de comunicación con la API de la FIFA.
- `database.py`: Gestión de persistencia en SQLite (Soporta IDs de texto).
- `betting.py`: Lógica matemática de cálculos de premios y multiplicadores.
- `cogs/`: Comandos de Discord organizados por módulos.
- `mantenimiento_db/`: Scripts para diagnósticos y reparaciones de la base de datos.
- `tests_simulacion/`: Suite de pruebas para verificar la lógica de pagos y el candado del minuto 90.

## 🔒 Seguridad y Robustez

- **IDs de Texto**: Migrado de IDs enteros a alfanuméricos para total compatibilidad con la FIFA.
- **Manejo de Errores API**: Sistema de reintentos automático para errores 500 y protección contra Rate Limits.
- **Cierre Rápido**: El bot detecta el estado `FINISHED` desde múltiples endpoints para asegurar que los premios se repartan apenas termina el encuentro.

## ⚖️ Licencia

Este proyecto es para uso personal y educativo. Todos los datos de partidos son propiedad de sus respectivos proveedores.
