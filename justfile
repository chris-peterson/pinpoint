# Which implementation to run
current := "1-python"

# Run the current implementation
run *args:
    just -f implementations/{{current}}/justfile run {{args}}

# Run any implementation by number-name
run-impl impl *args:
    just -f implementations/{{impl}}/justfile run {{args}}

# List available implementations
list:
    @ls implementations/
