# 2026 World Cup Predictor

2026 FIFA World Cup (USA/Mexico/Canada) four-layer fusion prediction model.

## Features

- **Elo Rating** — Dynamic team strength with host nation bonus, champion bonus
- **Dixon-Coles Poisson** — Expected goals with stage-aware adjustments
- **Monte Carlo Simulation** — 10,000 match simulations with environment factors
- **Bayesian Fusion** — Model + market odds weighted fusion
- **Extra Time & Penalties** — Knockout stage simulation
- **Kelly Staking** — Portfolio management with 6-filter risk control
- **Smart Data** — Local JSON + juhe API auto-sync
- **Excel Import** — Smart recognition, any format, incremental merge
- **Real-time Odds** — Multi-source aggregation with mock/real scrapers
- **Unit Tests** — 36 tests covering all core models
- **Docker Deploy** — One-command containerized deployment

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run Tests

```bash
pytest tests/test_models.py -v
```

## Docker Deploy

```bash
docker-compose up -d
```

Then open http://localhost:8501

## Tech Stack

Python + Streamlit + NumPy + Pandas + SciPy + pytest

## Data Sources

- juhe.cn API (standings, schedule, teams)
- Local JSON cache with auto-sync
- User-uploaded Excel odds & intelligence (smart format recognition)
- Real-time odds scraping (Oddschecker / Betfair / mock data)

## Project Structure

```
worldcup-predictor/
├── app.py                    # Streamlit main entry
├── config.py                 # Global configuration
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── data/
│   ├── local_data.py         # Local JSON data management
│   ├── api_client.py         # juhe.cn API client
│   ├── odds_importer.py      # Smart Excel/CSV odds import
│   ├── odds_scraper.py       # Web odds scraper (OddSlot + OddsFilter)
│   ├── data_pipeline.py      # Data cleaning & merging
│   └── cache.py              # File cache layer
├── model/
│   ├── elo_engine.py         # Elo rating engine
│   ├── poisson.py            # Dixon-Coles Poisson model
│   ├── monte_carlo.py        # Monte Carlo simulation
│   └── bayesian.py           # Bayesian fusion layer
├── strategy/
│   ├── kelly.py              # Kelly stake management
│   ├── filters.py            # Six-veto filters
│   └── risk_control.py       # Risk control module
├── realtime/
│   └── odds_scraper.py       # Real-time odds aggregator
├── ui/
│   └── components.py         # Reusable Streamlit components
├── tests/
│   └── test_models.py        # Unit tests (36 cases)
└── data_local/               # Runtime data cache
```

## Excel Import Format

The odds importer supports **any column naming** — no fixed template required.

Supported column names (case-insensitive):
- **Home team**: 主队 / Home Team / team1 / A队 / 队伍一 / 主场
- **Away team**: 客队 / Away Team / team2 / B队 / 队伍二 / 客场
- **Home odds**: 主胜赔率 / 1 / win / oh / 主胜 / 主
- **Draw odds**: 平局赔率 / X / draw / od / 平局 / 平
- **Away odds**: 客胜赔率 / 2 / lose / oa / 客胜 / 客
- **Date**: 日期 / date / time / match_date / 开赛时间
- **ID**: 编号 / id / match_id / 场次
- **Intel**: 情报 / intel / note / 备注 / 战报

You can upload **partial matchday data** — the system will auto-match to schedule and merge incrementally.

## License

MIT
