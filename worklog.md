# UltraBot Web - Work Log

## 2025-06-17: App entry point and test suite

### Files Created (11)
- `backend/app.py` – FastAPI application wiring all subsystems together
- `backend/tests/__init__.py` – empty test package init
- `backend/tests/test_fee_calculator.py` – 10 tests for NSE fee calculation
- `backend/tests/test_risk_gates.py` – 25 tests for all 13 risk gates
- `backend/tests/test_position_sizer.py` – 9 tests for dynamic Kelly sizing
- `backend/tests/test_partial_booker.py` – 10 tests for 3-level booking
- `backend/tests/test_paper_broker.py` – 11 tests for paper broker execution
- `backend/tests/test_error_engine.py` – 12 tests for error handling
- `backend/tests/test_market_hours.py` – 12 tests for market status
- `backend/tests/test_api_endpoints.py` – 20 tests for REST API
- `README.md` – Quick start guide

### Key Design Decisions in app.py
- `ErrorEngine()` is a singleton with no constructor args; callbacks set via setters
- `RiskEngine(risk_config)` takes a dict, NOT (settings, repo, daily_risk)
- `DailyRiskManager(config, total_capital)` takes dict + capital
- `PositionSizer(sizing_config, capital_config)` takes two separate dicts
- `PartialBooker(config)` takes a single dict
- `NSEFeeCalculator(brokerage_per_order=20.0)` takes a float, not a dict
- `BrokerFactory` is static (no instance needed), passed as class reference
- `SessionManager(repo_getter)` takes an async callable returning a Repository
- `MarketHours()` uses NSE defaults (no config dict needed)
- `UltraBotEngine.repository_getter` is a Callable, not a Repository instance
- `api.websocket` exports `router` (not `ws_router`)
- No `notifications/` module exists yet; telegram_bot/alert_manager not imported

### Bugs Found and Fixed
1. **SHORT P&L sign error** in `fees/nse_fee_calculator.py`: `calculate_net_pnl()` used `(buy_price - sell_price)` for SHORT direction, producing negative gross PnL for profitable shorts. Simplified to `(sell_price - buy_price)` for all directions.
2. **Stale bcrypt hash** in `api/dependencies.py`: The `_ADMIN_PASSWORD_HASH` didn't match "admin". Regenerated correct hash.

### Test Results
**115 tests passed** across 8 test files.

### Constructor Signatures Discovered
| Class | Signature |
|-------|------------|
| ErrorEngine | `()` (singleton, no args) |
| RiskEngine | `(config: Dict[str, Any])` |
| DailyRiskManager | `(config: Dict, total_capital: float = 100000)` |
| PositionSizer | `(config: Dict, capital_config: Dict)` |
| PartialBooker | `(config: Dict)` |
| NSEFeeCalculator | `(brokerage_per_order: float = 20.0)` |
| BrokerFactory | (static methods, no instance) |
| FeedManager | `(primary=None, backup=None)` |
| YahooHistoricalFeed | `()` |
| SessionManager | `(repo_getter: Callable)` |
| MarketHours | `(time params optional, defaults to NSE)` |
| KronosScanner | `(weights=None)` |
| StrategyRegistry | `()` |
| RegimeDetector | `()` |
| AdaptiveManager | `(config=None, registry=None, regime_detector=None)` |
| PerformanceTracker | `(repository=None, persist_interval=50)` |
| PaperBroker | `(initial_capital, fee_calculator=None, repository=None)` |
| UltraBotEngine | `(config, repository_getter, error_engine, risk_engine, position_sizer, partial_booker, daily_risk_manager, broker_factory, feed_manager, session_manager, market_hours=None, ws_manager=None)` |

---

## 2025-06-18: Support Packages (Notifications, News, Options, Scanner Fix)

### Files Created (12)

#### Notifications Package (4 files)
- `backend/notifications/__init__.py` – empty package init
- `backend/notifications/telegram_bot.py` – TelegramBot class with 9 async send methods: send_message, send_trade_fill, send_partial_booking, send_sl_hit, send_target_hit, send_morning_briefing, send_eod_report, send_error_alert, send_risk_alert. Uses Indian currency formatting. Graceful no-op when bot_token is empty.
- `backend/notifications/alert_manager.py` – AlertManager class routing 10 alert types (trade_fill, trade_exit, partial_booking, risk_event, error_alert, engine_status, regime_change, scan_complete, morning_briefing, eod_report) to Telegram and WebSocket channels based on config.
- `backend/notifications/eod_report.py` – EODReportGenerator class producing comprehensive EOD reports with P&L summary, strategy breakdown, sector breakdown, trade details, and formatted text. Uses Repository for data access.

#### News Package (3 files)
- `backend/news/news_engine.py` – NewsEngine class orchestrating concurrent fetch from 5 sources (EconomicTimes, Moneycontrol, GoogleFinance, NSECorporate, ResultCalendar), deduplication, analysis, and watchlist conversion.
- `backend/news/news_analyzer.py` – NewsAnalyzer class with keyword-based classification into 7 categories (earnings, corporate_action, regulatory, sector, macro, technical, general), 3 sentiment levels (positive/negative/neutral), and 3 impact levels (high/medium/low). Extracts NSE F&O symbols from text using direct and fuzzy name matching.
- `backend/news/news_to_watchlist.py` – NewsToWatchlist class converting classified news into watchlist additions. High impact → always add. Medium → add if positive sentiment or technical setup. Assigns BUY/SELL bias.

#### Options Package (6 files)
- `backend/options/__init__.py` – empty package init
- `backend/options/option_chain.py` – OptionChainFetcher using yfinance to fetch option chain data. Handles NSE stocks and indexes (NIFTY, BANKNIFTY). Auto-resolves nearest expiry.
- `backend/options/strike_selector.py` – StrikeSelector picking ATM or slightly OTM strikes based on direction, VIX level, and risk-reward ratio. Uses lot size from market_utils.
- `backend/options/greeks.py` – GreeksCalculator with full Black-Scholes implementation: delta, gamma, theta, vega, IV (Newton-Raphson), CDF/PDF. Uses RBI repo rate (7%) as risk-free rate.
- `backend/options/liquidity_filter.py` – LiquidityFilter filtering option chains by minimum OI, volume, bid-ask spread, and distance from ATM. Includes most-liquid-strike finder.
- `backend/options/options_risk.py` – OptionsRiskChecker validating capital limits (per-trade 5%, total 30%, max loss 2%) and generating warnings for high premium usage.

### Pre-existing Bugs Fixed (1)
1. **Syntax error in scanner/kronos/model_manager.py** – trailing `}` at line 130 causing SyntaxError. Removed the stray brace.

### Scanner Files Verified (Already Complete)
- `scanner/kronos/kronos_scanner.py` – Multi-factor scanner (305 lines, fully implemented)
- `scanner/kronos/signal_scorer.py` – Signal scoring with 5 factors (261 lines, fully implemented)
- `scanner/kronos/model_manager.py` – ML model manager with rule-based fallback (130 lines, fixed syntax)

### Verification
All 15 files pass `py_compile` syntax checks.
