import sys
import os
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app import app
from api.dependencies import get_current_user
from unittest.mock import patch

app.dependency_overrides[get_current_user] = lambda: "testuser"

def main():
    print("Initializing TestClient (this will trigger app lifespan)...")
    
    with patch("core.market_hours.MarketHours.get_market_status", return_value={"is_open": True, "session": "trading"}), \
         patch("core.market_hours.MarketHours.is_new_trade_window", return_value=True):
        with TestClient(app) as client:
            print("Starting engine in paper mode...")
            # Start engine with Breakout strategy
            resp = client.post("/api/engine/start", json={"mode": "paper", "broker": "paper", "strategies": ["Breakout"]}, headers={"Authorization": "Bearer test"})
            if resp.status_code != 200:
                print("Failed to start engine:", resp.status_code, resp.text)
            else:
                print("Engine start response:", resp.json())
            
            print("Waiting 15 seconds for the engine to scan symbols...")
            time.sleep(15)
            
            print("Fetching pending opportunities...")
            resp = client.get("/api/opportunities", headers={"Authorization": "Bearer test"})
            if resp.status_code == 200:
                opps = resp.json()
                print(f"Found {len(opps)} opportunities.")
                for i, opp in enumerate(opps[:3]):
                    print(f"--- Opportunity {i+1} ---")
                    print(f"Symbol: {opp.get('symbol')}")
                    print(f"Strategy: {opp.get('strategy')}")
                    print(f"Direction: {opp.get('direction')}")
                    print(f"Entry Price: {opp.get('entry_price')}")
                    print(f"Stop Loss: {opp.get('stop_loss')}")
                    print(f"Target: {opp.get('target')}")
                    print(f"Confidence: {opp.get('confidence')}")
            else:
                print("Failed to fetch opportunities:", resp.status_code, resp.text)
                
            print("Stopping engine...")
            client.post("/api/engine/stop", headers={"Authorization": "Bearer test"})

if __name__ == "__main__":
    main()
