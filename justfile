default: run

# Run the server
run *args:
    uv run python -m pinpoint --config config.yaml {{args}}

# Reset database, recreate sample library, and run
fresh *args:
    just reset
    just sample
    just run {{args}}

# Create the sample library
sample:
    rm -rf sample_library/ sample_output/
    uv run python scripts/create_sample_library.py --output sample_library

# Reset the database
reset:
    rm -f ~/.pinpoint/pinpoint.db

# Run tests
test *args:
    uv run --extra dev pytest -v {{args}}

# Lint
lint:
    uv run --extra dev ruff check src/

# Format
format:
    uv run --extra dev ruff format src/
