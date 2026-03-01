# trade_executor.py
from app import app
from services import execute_trades_for_recommendations

if __name__ == "__main__":
    with app.app_context():
        # execute_trades_for_today()
        execute_trades_for_recommendations()
