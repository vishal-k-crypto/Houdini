# Contributing to Houdini Agent

Thank you for your interest in contributing to Houdini Agent! This document provides guidelines and instructions to help you get started.

---

## How to Contribute

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally.
3. **Create a branch** for your feature or bug fix (`git checkout -b feature/my-feature`).
4. **Make your changes** and test them.
5. **Commit** your changes with a clear message.
6. **Push** your branch to your fork.
7. **Open a Pull Request** against the `main` branch.

---

## Development Setup

```bash
git clone https://github.com/vishal-k-crypto/Houdini.git
cd Houdini
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest ruff

# Optional: frontend setup
npm install --prefix frontend
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code.
- Run `ruff` before committing:
  ```bash
  ruff check src/ config/ tests/ --select E,F,W --ignore E501,E402,F401
  ```
- Keep functions focused and well-documented.
- Add tests for new features when possible.

---

## Frontend Contributions

If you are contributing to the frontend:

- Use TypeScript.
- Keep components modular and reusable.
- Run `npm run type-check --prefix frontend` and `npm run build --prefix frontend` before committing.
- Ensure the frontend works with both the dev server and the built daemon mode.

---

## Adding a New Provider

To add a new LLM provider:

1. Create an adapter in `src/providers/adapters/<provider>_adapter.py`.
2. Subclass `LLMProvider` from `src/providers/base.py`.
3. Define `__provider_id__` and `__provider_class__`.
4. Add required environment variables to `.env.example`.
5. Update `docs/PROVIDERS.md` and `README.md`.
6. Add a test if possible.

See [docs/PROVIDERS.md](../docs/PROVIDERS.md) for a full guide.

---

## Reporting Issues

When reporting an issue, please include:

- A clear description of the problem.
- Steps to reproduce.
- Expected vs. actual behavior.
- Your environment (Python version, OS, provider used).
- Relevant logs or screenshots.

---

## Pull Request Process

1. Ensure your branch is up to date with `main`.
2. Confirm tests pass locally.
3. Provide a clear PR description explaining what changed and why.
4. Link to any related issues.
5. Be responsive to review feedback.

---

## License

By contributing to this project, you agree that your contributions will be licensed under the MIT License.

---

Thank you for helping make Houdini Agent better!

---

## CI Note

The repository includes a GitHub Actions workflow at `.github/workflows/ci.yml` that runs Python lint/tests and Node.js frontend build/type-check. If you need to modify CI, ensure your OAuth token has `workflow` scope to push workflow changes, or ask a maintainer to apply the change.
