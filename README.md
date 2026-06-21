# 2026 World Cup Predictor

Four-layer fusion prediction model for the 2026 FIFA World Cup (USA/Mexico/Canada).

## Features

- **Elo Rating** - Dynamic team strength with host nation bonus, champion bonus
- **Dixon-Coles Poisson** - Expected goals with stage-aware adjustments
- **Monte Carlo Simulation** - 10,000 match simulations with environment factors
- **Bayesian Fusion** - Model + market odds weighted fusion
- **Extra Time & Penalties** - Knockout stage simulation
- **Kelly Staking** - Portfolio management with 6-filter risk control
- **Smart Data** - Local JSON + juhe API auto-sync
- **Excel Import** - Upload daily odds & intelligence

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Tech Stack

Python + Streamlit + NumPy + Pandas + SciPy

## Data Sources

- juhe.cn API (standings, schedule, teams)
- Local JSON cache with auto-sync
- User-uploaded Excel odds & intelligence
