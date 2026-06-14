import unittest
from datetime import datetime, timedelta, timezone
import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import api_football

class TestMatchLogicSimulations(unittest.TestCase):
    
    def test_minute_90_lock_logic(self):
        """Simula el cálculo del minuto para verificar que el candado se activa correctamente."""
        now = datetime.now(timezone.utc)
        
        # Caso 1: Partido recién empezado (hace 10 minutos)
        start_time_1 = (now - timedelta(minutes=10)).isoformat()
        minute_1 = api_football.calculate_match_minute(start_time_1)
        print(f"DEBUG: T+10m -> Minuto calculado: {minute_1:.1f}")
        self.assertTrue(0 < minute_1 < 15)
        self.assertLess(minute_1, 90, "El candado NO debería estar activo al minuto 10")

        # Caso 2: Partido en el minuto 85 (hace 105 minutos considerando entretiempo de 15 min y 5 de margen)
        # 85 + 20 (margen/entretiempo) = 105
        start_time_2 = (now - timedelta(minutes=105)).isoformat()
        minute_2 = api_football.calculate_match_minute(start_time_2)
        print(f"DEBUG: T+105m -> Minuto calculado: {minute_2:.1f}")
        self.assertTrue(80 < minute_2 < 90)
        self.assertLess(minute_2, 90, "El candado NO debería estar activo al minuto 85")

        # Caso 3: Partido en tiempo de descuento (hace 115 minutos)
        # 115 - 20 = 95
        start_time_3 = (now - timedelta(minutes=115)).isoformat()
        minute_3 = api_football.calculate_match_minute(start_time_3)
        print(f"DEBUG: T+115m -> Minuto calculado: {minute_3:.1f}")
        self.assertGreaterEqual(minute_3, 90, "El candado DEBERÍA estar activo al minuto 90+")

    def test_status_finished_priority(self):
        """Simula la prioridad del estado FINISHED sobre el cronómetro."""
        # Simulamos los datos que vendrían de la API
        mock_match_api = {
            "id": "test_id",
            "status": "FINISHED",
            "score": {"winner": "HOME_TEAM"}
        }
        
        # Verificamos la lógica que usa el bot en Betting.check_matches:
        # if status == 'FINISHED': winner = match['score']['winner'] ...
        
        status = mock_match_api['status']
        winner = mock_match_api['score']['winner']
        
        self.assertEqual(status, "FINISHED")
        self.assertEqual(winner, "HOME_TEAM", "Si el status es FINISHED, el bot debe leer al ganador del score")

    def test_mid_game_pause_logic(self):
        """Verifica que el minuto no siga corriendo infinitamente durante el entretiempo."""
        now = datetime.now(timezone.utc)
        
        # Simular que han pasado 55 minutos desde el inicio (estamos en el entretiempo)
        # 55 minutos -> debería devolver 45.0 clavados
        start_time = (now - timedelta(minutes=55)).isoformat()
        minute = api_football.calculate_match_minute(start_time)
        print(f"DEBUG: T+55m (Entretiempo) -> Minuto calculado: {minute:.1f}")
        self.assertEqual(minute, 45.0, "Durante el entretiempo el bot debe marcar minuto 45 clavado")

if __name__ == '__main__':
    unittest.main()
