import asyncio
import sys
sys.path.insert(0, '.')
from db.database import async_session_factory, init_db
from db.repository import Repository
from models.backtest_result import BacktestRequest
from api.routes.backtest import run_backtest
from fastapi import BackgroundTasks

async def main():
    await init_db()
    async with async_session_factory() as session:
        repo = Repository(session)
        req = BacktestRequest(
            strategy='breakout',
            symbol='RELIANCE',
            start_date='2025-01-01',
            end_date='2025-08-10',
            timeframe='5min',
            initial_capital=100000.0,
            parameters={'include_fees': True, 'apply_risk_gates': True}
        )
        bg = BackgroundTasks()
        try:
            res = await run_backtest(req=req, background_tasks=bg, username='admin', repo=repo)
            print('RESULT:', res)
        except Exception as e:
            print('EXCEPTION:', type(e), e)

if __name__ == '__main__':
    asyncio.run(main())
