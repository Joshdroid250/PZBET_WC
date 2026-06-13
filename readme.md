# ⚽ BetBot - Simulador de Apuestas para Discord

BetBot es un bot de Discord diseñado para gestionar un sistema de apuestas deportivas basado en un modelo de **Pozo Mutuo** con inyección de la casa. Incluye una interfaz moderna basada en componentes de Discord (Modals, Selects, Buttons) y un sistema robusto de apuestas combinadas (Parlays).

---

## 🚀 Funcionalidades Principales

### ⚽ Sistema de Apuestas
- **Apuestas Individuales**: Apuesta a ganador local, visitante o empate directamente desde menús interactivos.
- **Parlays (Combinadas)**: Constructor visual de apuestas múltiples. Multiplica tus ganancias acertando varios partidos en una sola jugada.
- **Cuotas Dinámicas**: Multiplicadores en tiempo real basados en el volumen total del pozo y la inyección de la casa.
- **Cashout Interactivo**: Retira tu apuesta antes de que el partido termine y recupera el 80% de tu inversión.

### 💰 Economía y Usuario
- **Bono de Bienvenida**: Recibe $100.00 monedas virtuales al registrarte con `!join`.
- **Recarga Diaria Automática**: Si tu balance llega a $0, el bot te regala **$15.00** cada 24 horas (persistente a reinicios).
- **Roles por Desempeño**: Sistema dinámico que asigna roles de Discord (ej: Broke, Gambler, Pro) según el balance del usuario.
- **Ranking Global (`!top`)**: Tabla de posiciones con los 10 usuarios más ricos del servidor.
- **Historial Detallado**: Consulta tus apuestas resueltas o mira el historial global con `!historial_all`.

### 🤖 Automatización y Optimización
- **Monitoreo Inteligente**: El bot optimiza las peticiones a la API deportiva, entrando en modo ahorro cuando no hay partidos próximos.
- **Anuncios Automáticos**: Notificaciones en tiempo real cuando un partido finaliza, mencionando a los ganadores.
- **Persistencia Total**: Base de datos SQLite para asegurar que ningún saldo o apuesta se pierda tras un reinicio.

---

## 🛠️ Instalación y Configuración

### Requisitos
- Python 3.10 o superior.
- Una cuenta en [API-Football](https://www.football-data.org/).
- Un Token de Bot de Discord (vía Discord Developer Portal).

### Pasos
1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-usuario/betbot.git
   cd betbot
   ```

2. **Crear entorno virtual e instalar dependencias:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configurar variables de entorno (`.env`):**
   Crea un archivo `.env` en la raíz con el siguiente contenido:
   ```env
   DISCORD_TOKEN=tu_token_aqui
   FOOTBALL_API_KEY=tu_api_key_aqui
   ANNOUNCEMENT_CHANNEL_ID=id_del_canal_de_anuncios
   HOUSE_INJECTION=50.0
   COMPETITION_CODE=PL  # Ejemplo: PL (Premier League), WC (Mundial), etc.
   ```

4. **Iniciar el bot:**
   ```bash
   python bot.py
   ```

---

## 📖 Comandos Disponibles

| Comando | Descripción |
| :--- | :--- |
| `!ayuda` | Muestra la lista interactiva de comandos. |
| `!reglas` | Explica el funcionamiento del pozo y premios. |
| `!join` | Crea tu cuenta inicial con $100. |
| `!balance` | Muestra tu saldo actual. |
| `!matches` | Abre el menú interactivo para apostar en próximos partidos. |
| `!parlay` | Inicia el constructor de apuestas combinadas. |
| `!mis_parlays`| Muestra el estado de tus combinadas activas. |
| `!cashout` | Abre el menú interactivo para retirar apuestas. |
| `!historial` | Consulta tus últimas 10 apuestas resueltas. |
| `!historial_all` | Muestra el historial global de todos los usuarios. |
| `!top` | Muestra el ranking de los 10 usuarios más ricos. |
| `!vivo` | Muestra partidos que se están jugando actualmente. |
| `!config_roles` | [ADMIN] Configura roles y umbrales (broke, gambler, pro). |
| `!debug_resolve` | [ADMIN] Fuerza la resolución de un partido y envía anuncios. |

---

## 🎭 Sistema de Roles por Desempeño
El bot permite motivar a los usuarios mediante la asignación automática de roles según su balance:
- **Broke**: Usuarios con saldo inicial o bajo.
- **Gambler**: Usuarios que han demostrado consistencia.
- **Pro**: La élite de los apostadores con los balances más altos.

**Configuración rápida para Administradores:**
```text
!config_roles gambler @RolGambler 500
!config_roles pro @RolPro 2000
```
*El bot asignará y quitará estos roles en tiempo real tras cada resolución de partido.*

---

## 🧪 Testing
El bot incluye una suite de pruebas para validar la lógica de negocio:
```bash
$env:PYTHONPATH="."; python tests/test_logic.py
```

---

## 📄 Licencia
Este proyecto está bajo la Licencia MIT. ¡Siéntete libre de usarlo y mejorarlo!

---
**Desarrollado para la competencia de Bots 2026.** 🏆

## 🤖 Créditos
Este bot ha sido desarrollado y optimizado con la asistencia de **Gemini**, la inteligencia artificial de Google, colaborando en la arquitectura, lógica de apuestas y diseño de la interfaz de usuario.
