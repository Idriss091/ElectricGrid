# AGENTS.md

## Project

We are building a pre-feasibility engine for flexible grid connections for BESS and large loads.

The product estimates:

- maximum firm connection capacity;
- maximum conditional capacity;
- recommended flexible connection envelope;
- expected curtailment risk;
- economic value of connecting now under constraints versus waiting for grid reinforcement.

## Product thesis

This is not a generic digital twin.
This is a buyer-side decision engine for flexible grid connection feasibility.

The expected output is an investment memo:

- go;
- no-go;
- go-with-conditions.

## Scientific goal

The research direction is:

"Probabilistic synthesis of flexible interconnection envelopes for BESS and large loads under network and economic uncertainty."

The scientific novelty is not hosting capacity alone.
The novelty is converting network capacity into a contractual and economic decision under uncertainty.

## Do not do

- Do not build a broad utility-wide digital twin.
- Do not claim this replaces official grid-connection studies.
- Do not target batteries + data centers + hydrogen + industry + utilities all at once.
- Do not invent physical assumptions silently.
- Do not hard-code unexplained constants.
- Do not create large abstractions before the MVP needs them.

## V1 focus

Start with BESS pre-feasibility.

The first useful workflow is:

1. load a benchmark network;
2. choose a candidate connection bus;
3. estimate approximate firm capacity;
4. estimate conditional capacity under simple constraints;
5. report binding constraints;
6. produce a simple go / no-go / go-with-conditions recommendation.

## Engineering rules

- Think before coding.
- Prefer simple, testable Python.
- Make small, surgical changes.
- Add tests for every meaningful function.
- Keep raw data, processed data, code, and results separate.
- Every experiment must be reproducible.

## Python conventions

- Use typed Python where practical.
- Use pytest for tests.
- Use ruff for linting.
- Prefer pure functions.
- Document power-system assumptions.
- Keep notebooks exploratory only; production logic belongs in src/.

## Done means

A task is done only when:

- tests pass;
- assumptions are documented;
- outputs are reproducible;
- changed files are summarized;
- remaining scientific uncertainty is clearly stated.
