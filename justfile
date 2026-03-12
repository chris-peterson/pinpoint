# Spec version and implementation to run
spec := "0.2"
impl := "1-hybrid"

# Run the current implementation
run *args:
    just -f implementations/{{spec}}/{{impl}}/justfile run {{args}}

# Reset database, recreate sample library, and run
fresh *args:
    just reset
    just sample
    just run {{args}}

# Run any implementation
run-impl spec impl *args:
    just -f implementations/{{spec}}/{{impl}}/justfile run {{args}}

# Create sample library (shared across implementations)
sample:
    rm -rf sample_library/ sample_output/
    cd implementations/{{spec}}/{{impl}} && uv run python ../../../scripts/create_sample_library.py --output ../../../sample_library

# Reset database for the current implementation
reset:
    just -f implementations/{{spec}}/{{impl}}/justfile reset

# Run tests for the current implementation
test *args:
    just -f implementations/{{spec}}/{{impl}}/justfile test {{args}}

# List available implementations
list:
    @echo "Spec versions:" && ls implementations/
    @echo "---"
    @echo "Current: {{spec}}/{{impl}}"
