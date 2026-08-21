# UltraBot Architecture Reference

Single-source technical reference for UltraBot generated directly from verified source files.

---

## 1. Risk Gates (G1 – G16)

The 16 risk gates are evaluated sequentially by `RiskEngine.validate()` (`ultrabot-web/backend/risk/risk_engine.py:90-100`). Each gate receives the risk config dictionary and extracts its parameters on construction.

| Gate | Class Name | Source File | Config Key(s) & Lookup | Literal Default | Logic & Checks |
|---|---|---|---|---|---|
| **G1** | `G1MaxPositions` | `ultrabot-web/backend/risk/gates/g1_max_positions.py:10-51` | `config.get("max_open_positions", 3)` | `3` | Fails if `open_count >= max_open_positions` (`:29`). |
| **G2** | `G2SectorConcentration` | `ultrabot-web/backend/risk/gates/g2_sector_concentration.py:12-57` | `config.get("max_per_sector", 2)`, `config.get("max_sector_concentration_pct", 40.0)` | `2`, `40.0%` | Calculates `effective_max = min(max_per_sector, max_positions * max_sector_pct / 100)`; fails if `current_count >= effective_max` (`:31-33`). |
| **G3** | `G3MaxPositionSize` | `ultrabot-web/backend/risk/gates/g3_max_position_size.py:11-93` | `config.get("max_per_position_pct")` or `config.get("max_position_size_pct")` or `config.get("max_capital_per_trade_pct")` or `25` | `25%` | Fails if `position_value > total_capital * (max_position_pct / 100.0)` (`:66-69`). |
| **G4** | `G4MaxDailyTrades` | `ultrabot-web/backend/risk/gates/g4_max_daily_trades.py:10-41` | `config.get("max_daily_trades", 10)` | `10` | Fails if `daily_trades >= max_daily_trades` (`:19`). |
| **G5** | `G5MaxDailyLoss` | `ultrabot-web/backend/risk/gates/g5_max_daily_loss.py:11-64` | `config.get("max_daily_loss_pct", 3)` | `3%` | Fails if cumulative `daily_pnl <= -(total_capital * max_daily_loss_pct / 100.0)` (`:38-40`). |
| **G6** | `G6CorrelationCheck` | `ultrabot-web/backend/risk/gates/g6_correlation_check.py:54-112` | `config.get("max_pairwise_correlation", config.get("max_correlation", 0.85))` | `0.85` | Checks pairwise empirical correlation against open positions; fails if `corr >= max_correlation` (`:90-92`). |
| **G7** | `G7VIXFilter` | `ultrabot-web/backend/risk/gates/g7_vix_filter.py:11-64` | `config.get("vix_threshold")` or `config.get("vix_high_threshold")` or `22.0`; `config.get("vix_extreme_threshold", 35.0)` | `22.0`, `35.0` | Fails with critical if `vix >= 35.0` (`:36`), warning if `vix > 22.0` (`:46`); passes if VIX is unavailable (`:24-32`). |
| **G8** | `G8TimeOfDay` | `ultrabot-web/backend/risk/gates/g8_time_of_day.py:15-75` | `config.get("new_trade_window_start", "09:30")`, `config.get("new_trade_window_end", "14:30")` | `"09:30"`, `"14:30"` IST | Fails if current IST time is not within `[09:30, 14:30]` (`:53-67`). |
| **G9** | `G9PriceMismatch` | `ultrabot-web/backend/risk/gates/g9_price_mismatch.py:11-71` | `config.get("price_mismatch_threshold_pct", 0.5)` | `0.5%` | Fails if `abs(entry_price - broker_ltp) / broker_ltp * 100.0 > 0.5` (`:43-45`). |
| **G10** | `G10MinConfidence` | `ultrabot-web/backend/risk/gates/g10_min_confidence.py:11-44` | `config.get("min_signal_confidence", 0.6)` | `0.6` | Fails if signal `confidence < min_confidence` (`:20`). |
| **G11** | `G11MaxDrawdown` | `ultrabot-web/backend/risk/gates/g11_max_drawdown.py:11-44` | `config.get("max_drawdown_pct", 5)` | `5%` | Fails if `current_drawdown_pct > max_drawdown_pct` (`:20`). |
| **G12** | `G12MarginCheck` | `ultrabot-web/backend/risk/gates/g12_margin_check.py:13-123` | `config.get("max_capital_usage_pct", 90)` | `90%` | Calculates required margin by segment (Options: 100%, Futures/Intraday: 20-25%); fails if `required_margin > available_margin` (`:84`) or `projected_capital_in_use > total_capital * 0.90` (`:99`). |
| **G13** | `G13DuplicateSignal` | `ultrabot-web/backend/risk/gates/g13_duplicate_signal.py:14-100` | `config.get("duplicate_signal_lookback_minutes", 15)` | `15 min` | Queries DB for signals on same symbol + direction within lookback cutoff; fails if duplicate found (`:51-66`). |
| **G14** | `G14StrategyBacktest` | `ultrabot-web/backend/risk/gates/g14_strategy_backtest.py:33-111` | `config.get("min_backtest_win_rate", 0.55)`, `config.get("min_backtest_profit_factor", 1.25)` | `0.55 (55%)`, `1.25` | Validates strategy backtest profile; fails if `win_rate < 0.55` (`:74`) or `profit_factor < 1.25` (`:87`). |
| **G15** | `G15VolumeLiquidity` | `ultrabot-web/backend/risk/gates/g15_volume_liquidity.py:12-56` | `config.get("min_volume_ratio", 1.0)` | `1.0x` | Fails if `volume_ratio < 1.0` (relative to 20-period average volume) (`:33`). |
| **G16** | `G16MultiTimeframe` | `ultrabot-web/backend/risk/gates/g16_multi_timeframe.py:11-76` | `config.get("require_trend_alignment", True)` | `True` | Fails if BUY/LONG and higher TF trend is Bearish (`:38`), or SELL/SHORT and higher TF trend is Bullish (`:47`), or neutral trend with breakout strategy and `confidence < 0.60` (`:58`). |

---

## 2. Database Schema (SQLAlchemy 2.0 ORM Models)

All models defined in `ultrabot-web/backend/db/migrations.py:18-335`. Primary keys use `Text` with UUID4 defaults (`_generate_uuid`). SQLite database located at `ultrabot-web/backend/data/ultrabot.db` (`ultrabot-web/backend/db/database.py:19`).

1. **`sessions`** (`ultrabot-web/backend/db/migrations.py:33-44`):
   `id` (Text, PK), `date` (Text), `start_time` (Text), `end_time` (Text, nullable), `status` (Text, default "running"), `engine_state` (Text, default "{}"), `metadata_json` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
2. **`trades`** (`ultrabot-web/backend/db/migrations.py:50-81`):
   `id` (Text, PK), `session_id` (Text, nullable), `signal_id` (Text, nullable), `position_id` (Text, nullable), `symbol` (Text), `direction` (Text), `strategy` (Text), `entry_price` (Float), `exit_price` (Float, nullable), `quantity` (Integer), `stop_loss` (Float, nullable), `target` (Float, nullable), `actual_sl` (Float, nullable), `actual_target` (Float, nullable), `status` (Text, default "OPEN"), `exit_reason` (Text, nullable), `entry_time` (Text), `exit_time` (Text, nullable), `pnl` (Float, default 0.0), `pnl_pct` (Float, default 0.0), `brokerage` (Float, default 0.0), `fees` (Float, default 0.0), `net_pnl` (Float, default 0.0), `holding_duration_seconds` (Integer, nullable), `notes` (Text, nullable), `tags` (Text, default "[]"), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
3. **`signals`** (`ultrabot-web/backend/db/migrations.py:87-110`):
   `id` (Text, PK), `session_id` (Text, nullable), `symbol` (Text), `direction` (Text), `strategy` (Text), `confidence` (Float, default 0.0), `entry_price` (Float, nullable), `stop_loss` (Float, nullable), `target` (Float, nullable), `risk_reward` (Float, nullable), `status` (Text, default "PENDING"), `rejection_reason` (Text, nullable), `kronos_score` (Float, nullable), `vix_at_signal` (Float, nullable), `regime_at_signal` (Text, nullable), `sector` (Text, nullable), `lot_size` (Integer, nullable), `signal_data` (Text, default "{}"), `risk_gate_results` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
4. **`positions`** (`ultrabot-web/backend/db/migrations.py:116-149`):
   `id` (Text, PK), `session_id` (Text, nullable), `trade_id` (Text, nullable), `signal_id` (Text, nullable), `symbol` (Text), `direction` (Text), `strategy` (Text), `entry_price` (Float), `current_price` (Float, nullable), `quantity` (Integer), `invested_amount` (Float, default 0.0), `stop_loss` (Float, nullable), `target` (Float, nullable), `initial_sl` (Float, nullable), `initial_target` (Float, nullable), `booked_qty` (Integer, default 0), `booked_pnl` (Float, default 0.0), `remaining_qty` (Integer, default 0), `status` (Text, default "OPEN"), `entry_time` (Text), `exit_time` (Text, nullable), `unrealized_pnl` (Float, default 0.0), `realized_pnl` (Float, default 0.0), `max_favorable_excursion` (Float, default 0.0), `max_adverse_excursion` (Float, default 0.0), `trailing_sl_active` (Boolean, default False), `current_trailing_sl` (Float, nullable), `partial_book_level` (Integer, default 0), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
5. **`watchlist`** (`ultrabot-web/backend/db/migrations.py:155-170`):
   `id` (Text, PK), `symbol` (Text, unique), `name` (Text), `sector` (Text, nullable), `lot_size` (Integer, nullable), `is_fno` (Boolean, default True), `is_active` (Boolean, default True), `added_at` (Text), `last_scanned_at` (Text, nullable), `last_signal_at` (Text, nullable), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
6. **`strategy_performance`** (`ultrabot-web/backend/db/migrations.py:176-200`):
   `id` (Text, PK), `strategy` (Text, unique), `total_trades` (Integer, default 0), `wins` (Integer, default 0), `losses` (Integer, default 0), `breakeven` (Integer, default 0), `win_rate` (Float, default 0.0), `avg_win` (Float, default 0.0), `avg_loss` (Float, default 0.0), `total_pnl` (Float, default 0.0), `max_win` (Float, default 0.0), `max_loss` (Float, default 0.0), `profit_factor` (Float, default 0.0), `avg_holding_seconds` (Float, default 0.0), `sharpe_ratio` (Float, default 0.0), `max_consecutive_wins` (Integer, default 0), `max_consecutive_losses` (Integer, default 0), `is_enabled` (Boolean, default True), `daily_stats` (Text, default "{}"), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
7. **`risk_events`** (`ultrabot-web/backend/db/migrations.py:206-220`):
   `id` (Text, PK), `session_id` (Text, nullable), `event_type` (Text), `severity` (Text, default "info"), `symbol` (Text, nullable), `strategy` (Text, nullable), `message` (Text), `value` (Float, nullable), `threshold` (Float, nullable), `action_taken` (Text, nullable), `extra` (Text, default "{}"), `created_at` (Text).
8. **`broker_credentials`** (`ultrabot-web/backend/db/migrations.py:226-237`):
   `id` (Text, PK), `broker_name` (Text, unique), `is_enabled` (Boolean, default False), `encrypted_credentials` (Text, default ""), `last_connected_at` (Text, nullable), `last_error` (Text, nullable), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
9. **`error_logs`** (`ultrabot-web/backend/db/migrations.py:243-263`):
   `id` (Text, PK), `error_code` (Text), `error_type` (Text), `severity` (Text, default "error"), `what_happened` (Text), `why_happened` (Text, nullable), `how_to_fix` (Text, nullable), `context` (Text, default "{}"), `stack_trace` (Text, nullable), `is_resolved` (Boolean, default False), `resolved_at` (Text, nullable), `resolution_note` (Text, nullable), `auto_recovery_attempted` (Boolean, default False), `auto_recovery_result` (Text, nullable), `session_id` (Text, nullable), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
10. **`backtest_runs`** (`ultrabot-web/backend/db/migrations.py:269-299`):
    `id` (Text, PK), `strategy` (Text), `symbol` (Text, nullable), `start_date` (Text), `end_date` (Text), `timeframe` (Text, default "5min"), `initial_capital` (Float, default 100000.0), `status` (Text, default "PENDING"), `total_trades` (Integer, default 0), `wins` (Integer, default 0), `losses` (Integer, default 0), `win_rate` (Float, default 0.0), `total_pnl` (Float, default 0.0), `max_drawdown_pct` (Float, default 0.0), `sharpe_ratio` (Float, default 0.0), `profit_factor` (Float, default 0.0), `avg_win` (Float, default 0.0), `avg_loss` (Float, default 0.0), `parameters` (Text, default "{}"), `results` (Text, default "{}"), `equity_curve` (Text, default "[]"), `error_message` (Text, nullable), `started_at` (Text, nullable), `completed_at` (Text, nullable), `duration_seconds` (Integer, nullable), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).
11. **`daily_summary`** (`ultrabot-web/backend/db/migrations.py:305-334`):
    `id` (Text, PK), `date` (Text, unique), `total_trades` (Integer, default 0), `wins` (Integer, default 0), `losses` (Integer, default 0), `breakeven` (Integer, default 0), `win_rate` (Float, default 0.0), `gross_pnl` (Float, default 0.0), `total_brokerage` (Float, default 0.0), `total_fees` (Float, default 0.0), `net_pnl` (Float, default 0.0), `net_pnl_pct` (Float, default 0.0), `max_win` (Float, default 0.0), `max_loss` (Float, default 0.0), `best_trade` (Text, nullable), `worst_trade` (Text, nullable), `strategies_used` (Text, default "[]"), `sector_pnl` (Text, default "{}"), `starting_capital` (Float, default 100000.0), `ending_capital` (Float, default 100000.0), `max_drawdown_pct` (Float, default 0.0), `regime` (Text, nullable), `vix_close` (Float, nullable), `notes` (Text, nullable), `extra` (Text, default "{}"), `created_at` (Text), `updated_at` (Text).

---

## 3. Engine State Machine

### Enums (`ultrabot-web/backend/core/engine_state.py:5-19`)
- **`EngineState`**: `"stopped"`, `"starting"`, `"running"`, `"paused"`, `"scanning"`, `"error"`
- **`EngineMode`**: `"paper"`, `"live"`

### Traced Lifecycle Transitions (`ultrabot-web/backend/core/engine.py`)
- **Initialization**: Initial state set to `EngineState.STOPPED` (`:97`).
- **`start()`**:
  - Validates `self.state in (EngineState.STOPPED, EngineState.ERROR)` (`:181`).
  - Sets `self.state = EngineState.STARTING` (`:184`).
  - Upon completing initialization tasks (feed connect, broker init, DB session start), sets `self.state = EngineState.RUNNING` (`:268`).
  - On unhandled exception during startup, sets `self.state = EngineState.ERROR` (`:302`).
- **`stop()`**:
  - If `self.state == EngineState.STOPPED`, returns immediately (`:329`).
  - Cancels running background tasks, closes positions/sessions, and sets `self.state = EngineState.STOPPED` (`:389`).
  - On unhandled exception during stop, sets `self.state = EngineState.ERROR` (`:411`).
- **`pause()`**:
  - Requires `self.state == EngineState.RUNNING` (`:431`).
  - Sets `self.state = EngineState.PAUSED` (`:434`).
- **`resume()`**:
  - Requires `self.state == EngineState.PAUSED` (`:447`).
  - Sets `self.state = EngineState.RUNNING` (`:450`).
- **`_main_loop()`**:
  - Runs loop while `self.state in (EngineState.RUNNING, EngineState.PAUSED, EngineState.SCANNING)` (`:487`).
  - Transitions to `self.state = EngineState.SCANNING` when scanning watchlist symbols and strategies (`:547`).
  - Transitions back to `self.state = EngineState.RUNNING` when the scan cycle completes (`:565`).
  - Transitions to `self.state = EngineState.ERROR` on unrecoverable loop exception (`:611`).

---

## 4. API Route Map

### Backend FastAPI Endpoints (`ultrabot-web/backend/app.py:252-278` & `api/routes/*.py`)

| Router File | Mounted Prefix | Method | Decorator Path | Full Route Path | Line |
|---|---|---|---|---|---|
| `app.py` | `""` | `GET` | `"/"` | `GET /` | `app.py:271` |
| `app.py` | `""` | `GET` | `"/health"`, `"/api/health"` | `GET /health`, `GET /api/health` | `app.py:276-277` |
| `auth.py` | `"/api/auth"` | `POST` | `"/login"` | `POST /api/auth/login` | `auth.py:47` |
| `auth.py` | `"/api/auth"` | `POST` | `"/logout"` | `POST /api/auth/logout` | `auth.py:86` |
| `auth.py` | `"/api/auth"` | `GET` | `"/me"` | `GET /api/auth/me` | `auth.py:108` |
| `dashboard.py` | `"/api/dashboard"` | `GET` | `""` | `GET /api/dashboard` | `dashboard.py:28` |
| `dashboard.py` | `"/api/dashboard"` | `GET` | `"/market-data"` | `GET /api/dashboard/market-data` | `dashboard.py:186` |
| `engine.py` | `"/api/engine"` | `POST` | `"/start"` | `POST /api/engine/start` | `engine.py:22` |
| `engine.py` | `"/api/engine"` | `POST` | `"/stop"` | `POST /api/engine/stop` | `engine.py:45` |
| `engine.py` | `"/api/engine"` | `POST` | `"/pause"` | `POST /api/engine/pause` | `engine.py:62` |
| `engine.py` | `"/api/engine"` | `POST` | `"/resume"` | `POST /api/engine/resume` | `engine.py:86` |
| `engine.py` | `"/api/engine"` | `GET` | `"/status"` | `GET /api/engine/status` | `engine.py:110` |
| `engine.py` | `"/api/engine"` | `GET` | `"/scan-telemetry"` | `GET /api/engine/scan-telemetry` | `engine.py:127` |
| `trades.py` | `"/api"` | `GET` | `"/trades"` | `GET /api/trades` | `trades.py:29` |
| `trades.py` | `"/api"` | `GET` | `"/trades/{trade_id}"` | `GET /api/trades/{trade_id}` | `trades.py:61` |
| `trades.py` | `"/api"` | `GET` | `"/positions"` | `GET /api/positions` | `trades.py:174` |
| `trades.py` | `"/api"` | `POST` | `"/positions/{position_id}/close"` | `POST /api/positions/{position_id}/close` | `trades.py:193` |
| `trades.py` | `"/api"` | `POST` | `"/positions/{position_id}/modify-sl"` | `POST /api/positions/{position_id}/modify-sl` | `trades.py:272` |
| `trades.py` | `"/api"` | `POST` | `"/positions/{position_id}/modify-target"` | `POST /api/positions/{position_id}/modify-target` | `trades.py:315` |
| `opportunities.py` | `"/api/opportunities"` | `GET` | `""` | `GET /api/opportunities` | `opportunities.py:27` |
| `opportunities.py` | `"/api/opportunities"` | `GET` | `"/invalidated"` | `GET /api/opportunities/invalidated` | `opportunities.py:49` |
| `opportunities.py` | `"/api/opportunities"` | `POST` | `"/{opportunity_id}/confirm"` | `POST /api/opportunities/{opportunity_id}/confirm` | `opportunities.py:66` |
| `opportunities.py` | `"/api/opportunities"` | `POST` | `"/{opportunity_id}/skip"` | `POST /api/opportunities/{opportunity_id}/skip` | `opportunities.py:110` |
| `opportunities.py` | `"/api/opportunities"` | `POST` | `"/{opportunity_id}/remind"` | `POST /api/opportunities/{opportunity_id}/remind` | `opportunities.py:147` |
| `strategies.py` | `"/api/strategies"` | `GET` | `""` | `GET /api/strategies` | `strategies.py:139` |
| `strategies.py` | `"/api/strategies"` | `PUT` | `"/{name}/toggle"` | `PUT /api/strategies/{name}/toggle` | `strategies.py:194` |
| `strategies.py` | `"/api/strategies"` | `PUT` | `"/{name}/params"` | `PUT /api/strategies/{name}/params` | `strategies.py:242` |
| `strategies.py` | `"/api/strategies"` | `GET` | `"/{name}/performance"` | `GET /api/strategies/{name}/performance` | `strategies.py:292` |
| `watchlist.py` | `"/api/watchlist"` | `GET` | `""` | `GET /api/watchlist` | `watchlist.py:70` |
| `watchlist.py` | `"/api/watchlist"` | `POST` | `"/add"` | `POST /api/watchlist/add` | `watchlist.py:103` |
| `watchlist.py` | `"/api/watchlist"` | `DELETE` | `"/{symbol}"` | `DELETE /api/watchlist/{symbol}` | `watchlist.py:152` |
| `watchlist.py` | `"/api/watchlist"` | `GET` | `"/universe"` | `GET /api/watchlist/universe` | `watchlist.py:186` |
| `risk.py` | `"/api/risk"` | `GET` | `"/status"` | `GET /api/risk/status` | `risk.py:59` |
| `risk.py` | `"/api/risk"` | `GET` | `"/gates"` | `GET /api/risk/gates` | `risk.py:154` |
| `risk.py` | `"/api/risk"` | `PUT` | `"/limits"` | `PUT /api/risk/limits` | `risk.py:257` |
| `risk.py` | `"/api/risk"` | `GET` | `"/events"` | `GET /api/risk/events` | `risk.py:315` |
| `brokers.py` | `"/api/brokers"` | `GET` | `""` | `GET /api/brokers` | `brokers.py:49` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/angel-one/credentials"` | `POST /api/brokers/angel-one/credentials` | `brokers.py:76` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/shoonya/credentials"` | `POST /api/brokers/shoonya/credentials` | `brokers.py:107` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/angel-one/test"` | `POST /api/brokers/angel-one/test` | `brokers.py:138` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/shoonya/test"` | `POST /api/brokers/shoonya/test` | `brokers.py:203` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/dhan/credentials"` | `POST /api/brokers/dhan/credentials` | `brokers.py:261` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/dhan/test"` | `POST /api/brokers/dhan/test` | `brokers.py:289` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/fyers/credentials"` | `POST /api/brokers/fyers/credentials` | `brokers.py:335` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/fyers/test"` | `POST /api/brokers/fyers/test` | `brokers.py:366` |
| `brokers.py` | `"/api/brokers"` | `GET` | `"/fyers/authorize"` | `GET /api/brokers/fyers/authorize` | `brokers.py:414` |
| `brokers.py` | `"/api/brokers"` | `GET` | `"/fyers/callback"` | `GET /api/brokers/fyers/callback` | `brokers.py:451` |
| `brokers.py` | `"/api/brokers"` | `GET` | `"/fyers/token-status"` | `GET /api/brokers/fyers/token-status` | `brokers.py:506` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/zerodha/credentials"`, `"/kite/credentials"` | `POST /api/brokers/zerodha/credentials`, `POST /api/brokers/kite/credentials` | `brokers.py:558-559` |
| `brokers.py` | `"/api/brokers"` | `POST` | `"/zerodha/test"`, `"/kite/test"` | `POST /api/brokers/zerodha/test`, `POST /api/brokers/kite/test` | `brokers.py:589-590` |
| `brokers.py` | `"/api/brokers"` | `PUT` | `"/active"` | `PUT /api/brokers/active` | `brokers.py:640` |
| `backtest.py` | `"/api/backtest"` | `POST` | `""` | `POST /api/backtest` | `backtest.py:397` |
| `backtest.py` | `"/api/backtest"` | `GET` | `"/status/{run_id}"` | `GET /api/backtest/status/{run_id}` | `backtest.py:435` |
| `backtest.py` | `"/api/backtest"` | `GET` | `"/results/{run_id}"` | `GET /api/backtest/results/{run_id}` | `backtest.py:508` |
| `backtest.py` | `"/api/backtest"` | `GET` | `"/history"` | `GET /api/backtest/history` | `backtest.py:525` |
| `errors.py` | `"/api/errors"` | `GET` | `""` | `GET /api/errors` | `errors.py:32` |
| `errors.py` | `"/api/errors"` | `GET` | `"/stats"` | `GET /api/errors/stats` | `errors.py:98` |
| `errors.py` | `"/api/errors"` | `GET` | `"/{error_id}"` | `GET /api/errors/{error_id}` | `errors.py:145` |
| `errors.py` | `"/api/errors"` | `PUT` | `"/{error_id}/resolve"` | `PUT /api/errors/{error_id}/resolve` | `errors.py:190` |
| `notifications.py` | `"/api/notifications"` | `GET` | `"/history"` | `GET /api/notifications/history` | `notifications.py:47` |
| `notifications.py` | `"/api/notifications"` | `GET` | `"/settings"` | `GET /api/notifications/settings` | `notifications.py:97` |
| `notifications.py` | `"/api/notifications"` | `PUT` | `"/settings"` | `PUT /api/notifications/settings` | `notifications.py:129` |
| `notifications.py` | `"/api/notifications"` | `POST` | `"/test"` | `POST /api/notifications/test` | `notifications.py:184` |
| `notifications.py` | `"/api/notifications"` | `POST` | `"/test-event"` | `POST /api/notifications/test-event` | `notifications.py:266` |
| `settings_api.py` | `"/api/settings"` | `GET` | `""` | `GET /api/settings` | `settings_api.py:53` |
| `settings_api.py` | `"/api/settings"` | `PUT` | `""` | `PUT /api/settings` | `settings_api.py:88` |
| `settings_api.py` | `"/api/settings"` | `GET` | `"/capital"` | `GET /api/settings/capital` | `settings_api.py:135` |
| `settings_api.py` | `"/api/settings"` | `PUT` | `"/capital"` | `PUT /api/settings/capital` | `settings_api.py:163` |
| `scanner.py` | `"/api/scanner"` | `GET` | `"/kronos"` | `GET /api/scanner/kronos` | `scanner.py:68` |
| `news.py` | `""` | `GET` | `"/api/news"` | `GET /api/news` | `news.py:127` |
| `news.py` | `""` | `GET` | `"/api/live-news"` | `GET /api/live-news` | `news.py:128` |
| `news.py` | `""` | `GET` | `"/api/news/sentiment"` | `GET /api/news/sentiment` | `news.py:129` |
| `news.py` | `""` | `GET` | `"/api/news-focus-stocks"`, `"/news-focus-stocks"` | `GET /api/news-focus-stocks`, `GET /news-focus-stocks` | `news.py:154-155` |
| `candles.py` | `""` | `GET` | `"/api/live-quotes"`, `"/live-quotes"` | `GET /api/live-quotes`, `GET /live-quotes` | `candles.py:133-134` |
| `candles.py` | `""` | `GET` | `"/api/candles"`, `"/candles"` | `GET /api/candles`, `GET /candles` | `candles.py:235-236` |
| `websocket.py` | `""` | `WebSocket` | `"/ws"` | `WS /ws` | `websocket.py:264` |

### Frontend Pages (`src/app/`)
- `/` (`src/app/page.tsx:427`): `DashboardPage`
- `/trades` (`src/app/trades/page.tsx:1196`): `TradesPage`
- `/opportunities` (`src/app/opportunities/page.tsx:1052`): `OpportunitiesPage`
- `/risk` (`src/app/risk/page.tsx:117`): `RiskDashboardPage`
- `/strategies` (`src/app/strategies/page.tsx:217`): `StrategiesPage`
- `/watchlist` (`src/app/watchlist/page.tsx:121`): `WatchlistPage`
- `/backtest` (`src/app/backtest/page.tsx:1186`): `BacktestPage`
- `/errors` (`src/app/errors/page.tsx:220`): `ErrorsPage`
- `/news` (`src/app/news/page.tsx:31`): `NewsPage`
- `/settings` (`src/app/settings/page.tsx:242`): `SettingsPage`
- `/login` (`src/app/login/page.tsx:15`): `LoginPage`
