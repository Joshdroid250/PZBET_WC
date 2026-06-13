# ⚽ BetBot - Simulador de Apuestas para Discord

BetBot es un bot de Discord diseñado para gestionar un sistema de apuestas deportivas basado en un modelo de **Pozo Mutuo** con inyección de la casa. Incluye una interfaz moderna basada en componentes de Discord (Modals, Selects, Buttons) y un sistema robusto de apuestas combinadas (Parlays).

---

## 🚀 Funcionalidades Principales

### ⚽ Sistema de Apuestas
- **Apuestas Individuales**: Apuesta a ganador local, visitante o empate desde menús privados.
- **Parlays (Combinadas)**: Constructor visual para agrupar varios partidos en una sola jugada y maximizar ganancias.
- **Cuotas Dinámicas**: Multiplicadores en tiempo real que se ajustan según el volumen de apuestas y el bono de la casa.
- **Análisis de Pozo (`/pozo`)**: Herramienta pública para ver la liquidez y las cuotas actuales de cualquier partido.
- **Cashout**: Retira tus jugadas antes del pitazo final y recupera el 80% de tu dinero.

### 💰 Economía y Usuario
- **Bono de Bienvenida**: Recibe $100.00 monedas virtuales al unirte con `/join`.
- **Recarga Diaria Automática**: Si te quedas sin fondos, el bot te regala **$15.00** cada 24 horas (persistente a reinicios).
- **Roles por Desempeño**: Sistema automático de rangos de Discord (Broke, Gambler, Pro) según tu balance actual.
- **Ranking Global (`/top`)**: Tabla de posiciones pública para ver quién es el apostador más exitoso del servidor.

### 🤖 Automatización y UX
- **Marcador en Vivo**: Un mensaje dinámico en el canal de anuncios que se actualiza automáticamente y se borra al terminar el partido.
- **Mensajes Efímeros**: Los menús de apuestas son privados; solo tú puedes verlos e interactuar con ellos, manteniendo el chat limpio y seguro.
- **Sincronización Total**: Comandos Slash modernizados con autocompletado y sugerencias nativas.

---

## 🛠️ Instalación y Configuración

### Requisitos
- Python 3.10 o superior.
- Una cuenta en [API-Football](https://www.football-data.org/).
- Token de Bot con Intents de `Message Content` y `Server Members`.

### Pasos
1. **Clonar e Instalar:**
   ```bash
   git clone https://github.com/tu-usuario/betbot.git
   pip install -r requirements.txt
   ```

2. **Configurar `.env`:**
   ```env
   DISCORD_TOKEN=...
   FOOTBALL_API_KEY=...
   ANNOUNCEMENT_CHANNEL_ID=...
   HOUSE_INJECTION=50.0
   COMPETITION_CODE=PL
   ```

3. **Migrar e Iniciar:**
   ```bash
   python migrate_db.py
   python bot.py
   ```

---

## 📖 Comandos Disponibles

| Comando | Visibilidad | Descripción |
| :--- | :--- | :--- |
| `/join` | Privado | Regístrate y recibe $100. |
| `/balance` | Privado | Mira tu saldo actual. |
| `/matches` | Privado | Menú para apostar en próximos partidos. |
| `/vivo` | Privado | Mira partidos que se juegan ahora mismo. |
| `/parlay` | Privado | Constructor de apuestas combinadas. |
| `/pozo <id>` | **Público** | Análisis de volumen y cuotas del partido. |
| `/top` | **Público** | Ranking de los 10 más ricos. |
| `/historial_all`| **Público** | Historial de apuestas de todo el servidor. |
| `/ayuda` | Privado | Guía interactiva de comandos. |
| `/config_roles` | Admin | Configura roles por balance. |

---

## 🤖 Créditos
Este bot ha sido desarrollado y optimizado con la asistencia de **Gemini**, la inteligencia artificial de Google, colaborando en la arquitectura asíncrona, lógica de apuestas y diseño de la interfaz de usuario.
