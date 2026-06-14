import asyncio
import database
import os

async def test():
    # Ensure we use the real db
    database.DB_PATH = 'betbot.db'
    print(f"Checking database at {database.DB_PATH}...")
    
    try:
        await database.init_db()
        print("DB Init OK")
        
        # Test a dummy user ID
        user_id = 99999999
        print(f"Testing for user {user_id}...")
        
        active = await database.get_user_active_bets(user_id)
        print(f"Active bets query OK: {active}")
        
        history = await database.get_user_history(user_id)
        print(f"History query OK: {history}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test())
