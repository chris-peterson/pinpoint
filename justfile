# Which implementation to run
current := "1-python"

# Run the current implementation
run *args:
    just -f implementations/{{current}}/justfile run {{args}}

# Reset database, recreate sample library, and run
fresh *args:
    just reset
    just sample
    just run {{args}}

# Run any implementation by number-name
run-impl impl *args:
    just -f implementations/{{impl}}/justfile run {{args}}

# Create sample library (shared across implementations)
sample:
    rm -rf sample_library/ sample_output/
    cd implementations/{{current}} && uv run python ../../scripts/create_sample_library.py --output ../../sample_library

# Reset database for the current implementation
reset:
    just -f implementations/{{current}}/justfile reset

# Run tests for the current implementation
test *args:
    just -f implementations/{{current}}/justfile test {{args}}

# List available implementations
list:
    @ls implementations/
