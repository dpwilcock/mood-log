# Mood Log & Modeling

Low friction way to record how the day has been - used with an Ai/LLM agent and messaging software - record verbally, quickly, low friction - makes it easy to just do - with reminder at the right time of day for you.   Low friction is essential to getting a new daily habit done.   This works for me, I hope it can work for you.

The tool Parses mood check-ins, process them with LLM/rule-based pipelines, and model mood vs. physiological/workload data.

Tools for logging and analyzing periodic mood check-ins (e.g. a 1-10 score with a comment), processing them through rule-based or LLM pipelines, and modeling mood against workload and health metrics.

## Components

- `mood_parser.py` — parse raw mood text into (score, comment, timestamp); optional LLM commentary
- `process_moods_*.py` — batch processors: Anthropic, GenAI, Ollama variants (choose your backend)
- `mood_modeling_v2.py` — correlation/regression modeling of mood vs. workload and health features

## Requirements

- Python 3.9+
- `pip install psycopg2-binary anthropic` (or ollama for the local variant)

## Configuration (environment variables)

| Variable | Purpose |
|----------|---------|
| `MOOD_DIR` | Directory containing mood notes (`.md` files) to ingest |
| `MOOD_NOTES_DIR` | Directory for `mood_parser.py`'s file-based mode (default `~/mood-notes`) |
| `PGDATABASE` | PostgreSQL database name (default: `postgres`) |
| `ANTHROPIC_API_KEY` | Anthropic API key (for the LLM processors) |
| `GEMINI_MODEL` | Gemini model to use (default `gemini-2.0-flash`) |
| `OLLAMA_MODEL` | Ollama model to use (default `llama3.2:latest`) |
| `AIRTHINGS_DEVICE_ID` | Airthings device ID used in mood modeling (optional) |
| `HRV_LOW_THRESHOLD` / `RHR_HIGH_THRESHOLD` | Physiology warning thresholds (defaults 24 / 75) |

## Setup

```bash
psql -U postgres -d postgres -f schema.sql
```

## Usage

```bash
# Parse a single mood entry from inline text (prints extracted JSON)
python3 mood_parser.py "7/10 Felt great after the ride"

# Batch-process mood notes from MOOD_DIR with an LLM
python3 process_moods_anthropic.py    # Claude
python3 process_moods_genai.py        # Gemini
python3 process_moods_ollama.py       # local Ollama

# Run the mood vs. workload model
python3 mood_modeling_v2.py
```

`mood_parser.py` also supports `all` (process every `.md` in `MOOD_NOTES_DIR`) and
`process_moods_*.py` all process every file in `MOOD_DIR`.

The pattern is deliberately backend-agnostic: swap the processor to match whatever scoring or model service you prefer.
