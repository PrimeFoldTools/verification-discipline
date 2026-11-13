.PHONY: test mutations self-check all

# No dependencies beyond Python 3 + pytest. Nothing here touches a network or a
# private store; every test injects a fake client.
test:
	python3 -m pytest -q

# Prove the tests can actually fail: flip a load-bearing line, watch the suite
# go red, restore, confirm green.
mutations:
	python3 mutation_check.py

# Run try_on_your_repo.py on this example project (plants bugs in a copy).
self-check:
	python3 try_on_your_repo.py . --test "python3 -m pytest -q -x -p no:cacheprovider" --paths cli.py gate.py json_safe.py --max 8

all: test mutations
