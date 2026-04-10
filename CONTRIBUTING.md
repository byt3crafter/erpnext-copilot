# Contributing to ERPNext AI Bots

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.10+
- A working [Frappe Bench](https://frappeframework.com/docs/user/en/installation) setup
- ERPNext 15 installed
- An AI provider account (OpenAI or Anthropic)

### Development Setup

1. Fork the repository and clone your fork:

```bash
git clone https://github.com/YOUR_USERNAME/erpnext_ai_bots.git
```

2. Install the app in development mode:

```bash
cd ~/frappe-bench
bench get-app /path/to/your/erpnext_ai_bots
bench --site your-site.localhost install-app erpnext_ai_bots
bench --site your-site.localhost migrate
```

3. Start the development server:

```bash
bench start
```

### Running Tests

```bash
cd ~/frappe-bench
bench --site your-site.localhost run-tests --app erpnext_ai_bots
```

Or with pytest directly:

```bash
cd apps/erpnext_ai_bots
pytest
```

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/byt3crafter/erpnext_ai_bots/issues) to report problems
- Include your Frappe/ERPNext version, Python version, and AI provider
- Include steps to reproduce the issue
- Include relevant error messages or logs

### Suggesting Features

- Open a GitHub Issue with the `enhancement` label
- Describe the use case and why it would be valuable
- If it involves a new AI tool, describe what inputs/outputs you'd expect

### Submitting Code

1. **Create a branch** from `community`:

```bash
git checkout community
git pull origin community
git checkout -b feature/your-feature-name
```

2. **Make your changes** following the code style below

3. **Write or update tests** if applicable

4. **Test your changes**:

```bash
bench --site your-site.localhost run-tests --app erpnext_ai_bots
```

5. **Commit with a clear message**:

```bash
git commit -m "feat: add purchase analytics tool"
```

6. **Push and open a Pull Request** against the `community` branch

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation only
- `refactor:` — Code change that neither fixes a bug nor adds a feature
- `test:` — Adding or updating tests
- `chore:` — Maintenance tasks

## Code Style

### Python

- Follow PEP 8
- Use type hints where they add clarity
- Keep functions focused — one tool, one job
- All AI tools must inherit from the base tool class in `tools/base.py`

### JavaScript

- Follow Frappe's JS conventions
- Use the existing patterns in `public/js/`

### Adding a New AI Tool

1. Create a new file in the appropriate category folder under `erpnext_ai_bots/tools/`:

```
tools/
  accounting/    # Financial tools
  hr/            # Human resources tools
  stock/         # Inventory tools
  sales/         # Sales tools
  purchasing/    # Procurement tools
  crm/           # CRM tools
  project/       # Project management tools
  asset/         # Asset management tools
  core/          # Generic CRUD / utility tools
  meta/          # Orchestration tools (subagent, scheduling)
```

2. Your tool must:
   - Inherit from the base tool class
   - Define a clear JSON schema for parameters
   - Respect ERPNext permissions (use the permission guard)
   - Return structured data (not raw HTML)
   - Handle errors gracefully
   - Be registered in the category's `__init__.py`

3. Add tests in `erpnext_ai_bots/tests/`

## Project Structure

```
erpnext_ai_bots/
  agent/          # Orchestrator, context builder, streaming
  ai_bots/        # Frappe DocTypes (Settings, Sessions, Audit, etc.)
  api/            # HTTP endpoints (chat, OAuth)
  config/         # Frappe app config
  guards/         # Rate limiter, permission checks
  licensing/      # Provider auth (OpenAI OAuth, etc.)
  public/         # Frontend JS/CSS
  tests/          # Test suite
  tools/          # All AI tools (organized by ERPNext module)
  utils/          # Shared utilities (prompt defense, token counter)
```

## Questions?

- Open an issue on GitHub
- Email: dovik@micinthe.com

Thank you for helping make ERPNext smarter!
