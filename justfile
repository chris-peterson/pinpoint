# Run the server (alias for `run`)
default: run

# Run the server
run *args:
    uv run python -m pinpoint --config config.yaml {{args}}

# Reset database, recreate sample library, and run
fresh *args:
    just reset
    just sample
    just run {{args}}

# Populate the sample library's _input/ tree
sample:
    rm -rf sample_output/
    uv run python scripts/create_sample_library.py --output sample_output

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

# Stage the docs site (copies SPEC.md to where the sidebar links it)
docs:
    cp SPEC.md docs/spec.md

# Preview the docs site locally
preview-docs: docs
    npx docsify-cli serve docs --open
