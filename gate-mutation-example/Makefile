.PHONY: test mutations all

# No dependencies beyond Python 3 + pytest. Nothing here touches a network or a
# private store; every test injects a fake client.
test:
	python3 -m pytest -q

# Prove the tests can actually fail: flip a load-bearing line, watch the suite
# go red, restore, confirm green.
mutations:
	python3 mutation_check.py

all: test mutations
