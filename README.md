# Quant Trading System

Project 1 of 5: environment setup and data pipeline.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in the API credentials in `.env` before using Alpaca.

## Features

- Standardised OHLCV fetchers for Yahoo Finance, CCXT, Alpaca, and local CSV files
- Parquet-backed cache organised by symbol and timeframe
- Retry logic with cached-data fallback through the data store
- Environment-driven configuration via `python-dotenv`

## Usage

```python
from data.storage.data_store import DataStore

store = DataStore()
frame = store.get("SPY", "1d", "2020-01-01", "2025-12-31")
```

## Tests

```powershell
python -m pytest tests -v
```
