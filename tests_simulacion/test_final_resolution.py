import unittest
import json
import sys
import os

# Simulación de la estructura de la FIFA API que el usuario proporcionó
FIFA_FINISHED_JSON = {
    "matches": [
        {
            "id": "znr9ser4v1de",
            "status": "FINISHED",
            "homeTeam": {"name": "Mexico"},
            "awayTeam": {"name": "South Africa"},
            "score": {
                "winner": "HOME_TEAM",
                "fullTime": {"home": 2, "away": 0}
            }
        },
        {
            "id": "m889n7jrhmto",
            "status": "FINISHED",
            "homeTeam": {"name": "Haiti"},
            "awayTeam": {"name": "Scotland"},
            "score": {
                "winner": "AWAY_TEAM",
                "fullTime": {"home": 0, "away": 1}
            }
        }
    ]
}

# Simulación de lo que el bot tiene en su Base de Datos interna (Active Matches)
INTERNAL_DB_MATCHES = [
    ("znr9ser4v1de", "Mexico", "South Africa"), # Coincide por ID
    ("m889n7jrhmto", "Haiti", "Scotland"),      # Coincide por ID
    ("other_id", "Netherlands", "Japan")        # No ha terminado aún
]

class TestFinalMatchResolution(unittest.TestCase):
    
    def test_payout_logic_simulation(self):
        """Simula paso a paso cómo el bot procesaría el JSON de la FIFA."""
        print("\n🚀 INICIANDO SIMULACIÓN DE CIERRE DE PARTIDOS...")
        
        fifa_matches = FIFA_FINISHED_JSON["matches"]
        resolved_count = 0

        for f_match in fifa_matches:
            f_id = f_match["id"]
            f_home = f_match["homeTeam"]["name"]
            f_away = f_match["awayTeam"]["name"]
            f_status = f_match["status"]
            f_winner = f_match["score"]["winner"]
            f_score_str = f"{f_match['score']['fullTime']['home']}-{f_match['score']['fullTime']['away']}"

            # 1. El bot busca si este partido de la FIFA está en nuestra DB
            internal_match = next((m for m in INTERNAL_DB_MATCHES if m[0] == f_id), None)
            
            if internal_match and f_status == 'FINISHED':
                resolved_count += 1
                print(f"✅ [MATCH FOUND] ID: {f_id} | {f_home} vs {f_away}")
                print(f"   ➔ Estado: {f_status}")
                print(f"   ➔ Marcador: {f_score_str}")
                print(f"   ➔ Ganador detectado para pagos: {f_winner}")
                
                # Verificación de lógica de ganador
                self.assertIn(f_winner, ["HOME_TEAM", "AWAY_TEAM", "DRAW"])
                
                if f_id == "znr9ser4v1de":
                    self.assertEqual(f_winner, "HOME_TEAM", "México debería ser el ganador")
                if f_id == "m889n7jrhmto":
                    self.assertEqual(f_winner, "AWAY_TEAM", "Escocia debería ser el ganador")

        print(f"\n📊 Simulación finalizada. Partidos resueltos correctamente: {resolved_count}")
        self.assertEqual(resolved_count, 2)

if __name__ == '__main__':
    unittest.main()
