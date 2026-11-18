# Orchestrates

This repository contains two independent projects built for HackerRank Orchestrate challenges. Each project has its own problem statement, implementation, input data, and output format.

## Projects

### September 2026 — Buy or Wait?

An AI-assisted financial affordability agent. It evaluates a user's request against their balance, financial events, priorities, messages, images, and payment options, then recommends a safe payment decision.

- Project: [`September-2026/September/`](./September-2026/September/)
- Project guide: [`README.md`](./September-2026/September/README.md)
- Challenge specification: [`problem_statement.md`](./September-2026/September/problem_statement.md)
- Main entry point: [`code/main.py`](./September-2026/September/code/main.py)

### October 2026 — Ghost Data Still Exists

An AI-assisted data-deletion auditor. It checks whether deletion requests were actually completed, identifies remaining data or recreation risks, and produces remediation and verification steps.

- Project: [`October-2026/october/hackerrank-orchestrate-october26/`](./October-2026/october/hackerrank-orchestrate-october26/)
- Project guide: [`README.md`](./October-2026/october/hackerrank-orchestrate-october26/README.md)
- Challenge specification: [`problem_statement.md`](./October-2026/october/hackerrank-orchestrate-october26/problem_statement.md)
- Main entry point: [`code/main.py`](./October-2026/october/hackerrank-orchestrate-october26/code/main.py)

## Running a project

The projects are independent. Open a terminal in the relevant project directory and follow that project's README for setup, inputs, and output requirements.

For either Python entry point, the basic command is:

```bash
python code/main.py
```

Run it from the project directory so relative paths to `dataset/` and `output.csv` resolve correctly. The September project writes its predictions to its project-root `output.csv`; the October project does the same.

## Repository layout

```text
Orchestrates/
├── README.md
├── September-2026/
│   └── September/
│       ├── code/
│       ├── dataset/
│       ├── problem_statement.md
│       └── output.csv
└── October-2026/
    └── october/
        └── hackerrank-orchestrate-october26/
            ├── code/
            ├── dataset/
            ├── problem_statement.md
            └── output.csv
```

## Data and credentials

The datasets are synthetic challenge data. Keep API keys and other credentials in local environment files or environment variables; do not commit them. The project-specific `.gitignore` files exclude `.env` files.
