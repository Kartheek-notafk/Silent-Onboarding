# Local Documentation Knowledge Base for Onboarding & Environment Setup

## Environment Setup Guide

### 1. Python Environment Setup
- **Required Python Version:** Python 3.10 or higher.
- **Virtual Environment Creation:**
  ```bash
  python -m venv venv
  # On Windows:
  .\venv\Scripts\activate
  # On macOS/Linux:
  source venv/bin/activate
  ```
- **Installing Dependencies:**
  ```bash
  pip install -r requirements.txt
  ```

### 2. Discord Bot Setup
- Go to [Discord Developer Portal](https://discord.com/developers/applications).
- Create a new Application and add a Bot user.
- Under **Privileged Gateway Intents**, enable **Message Content Intent**.
- Copy the Bot Token into your `.env` file (`DISCORD_TOKEN=...`).
- Invite the bot to your test server with `bot` and `application.commands` scopes.

### 3. Database Configuration
- The project uses **SQLite** (`app.db`) managed via **SQLAlchemy**.
- No additional database server installation is required.

### 4. Common Onboarding Issues & Troubleshooting
- **`ModuleNotFoundError: No module named 'fastapi'`**: Ensure your virtual environment is activated before running the project.
- **Discord Bot not reading messages**: Ensure **Message Content Intent** is enabled in the Discord Developer Portal.
- **Channel Names**: Ensure server channels match `.env` (`onboarding-help` and `doc-approvals`).
