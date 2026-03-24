# Octopal GEMINI.md

This document provides a comprehensive overview of the Octopal project, its architecture, and instructions for building, running, and developing the application.

## Project Overview

Octopal is a sophisticated AI agent platform built in Python. It is designed around a "Octo and Workers" architecture, where a central "Octo" orchestrates tasks and delegates them to specialized "Workers." The platform is highly modular, extensible, and designed for complex, multi-step tasks.

### Core Components

*   **Octo:** The central orchestrator of the Octopal platform. The Octo receives messages (from a Telegram bot), decides how to handle them, and dispatches tasks to Workers. It uses a large language model (LLM) to make decisions and communicate with the user.
*   **Workers:** Specialized agents that perform specific tasks. Workers are defined by a `WorkerSpec` and can be granted specific capabilities, such as network access or filesystem access. They can be run in the same environment as the Octo or as separate Docker containers.
*   **Skills:** The capabilities of Workers are defined by "Skills." A Skill is a bundle of code and metadata that allows a Worker to perform a specific action. This skill-based architecture makes the platform highly extensible.
*   **Policy Engine:** A security component that controls the capabilities of Workers. The Policy Engine ensures that Workers only have the permissions they need to perform their tasks.
*   **Memory:** A service that provides contextual memory to the Octo and Workers. This allows the agent to maintain a consistent state and remember previous interactions.
*   **Telegram Bot:** The primary user interface for the Octopal platform. Users interact with the Octo through a Telegram bot.
*   **Gateway:** A web API (built with FastAPI) that provides an additional interface to the Octopal platform.

### Technologies

*   **Python:** The core language of the project.
*   **Typer:** Used for building the command-line interface.
*   **FastAPI:** Used for building the web API gateway.
*   **Pydantic:** Used for data validation and settings management.
*   **Docker:** Used for containerizing Workers and the main application.
*   **Telegram Bot API:** For user interaction.
*   **LLM Integration:** The platform is designed to integrate with various LLMs, including ZAI and OpenAI.

## Building and Running

### Prerequisites

*   Python 3.12+
*   Docker
*   An environment file with the necessary API keys and configuration.

### Getting Started

1.  **Create an environment file:** Copy `.env.example` to `.env` and fill in the required API keys and configuration values.

    ```bash
    cp .env.example .env
    ```

2.  **Install dependencies:** It is recommended to use a virtual environment.

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```

3.  **Run the application:** The main entry point is the `octopal start` command.

    ```bash
    octopal start
    ```

### Docker

The application can also be run using Docker Compose.

```bash
docker-compose up
```

This will build the `octopal` service and run the `octopal start` command.

## Development Conventions

*   **Modular Architecture:** The codebase is organized into distinct modules with clear responsibilities. When adding new features, follow this modular pattern.
*   **Dependency Injection:** The `Octo` and `WorkerRuntime` classes are initialized with their dependencies, which makes the code easier to test and maintain.
*   **Skills:** To extend the agent's capabilities, create a new Skill. A Skill consists of a `skill.json` file, a `SKILL.md` file, and the Python code that implements the skill's logic.
*   **Intents and Permits:** For actions that require special permissions, use the "Intent and Permit" system. A Worker requests an "Intent," and the `PolicyEngine` issues a "Permit" if the action is allowed.
*   **Testing:** (No testing framework is explicitly defined in the project, but `pytest` is a common choice for Python projects. When adding new features, consider adding tests to ensure correctness.)
*   **Linting and Formatting:** (No linting or formatting tools are explicitly defined, but `black` and `ruff` are recommended for maintaining a consistent code style.)

## Additional Information

The `AGENTS.md` file in the root of the repository contains additional guidelines for project structure, build commands, coding style, and commit/pull request conventions. It is recommended to review this file for a more detailed understanding of the project's development practices.
