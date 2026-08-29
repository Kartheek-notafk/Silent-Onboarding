# Silent Onboarding — External Integrations & Notion Pusher Guide

This guide contains the task breakdown and copy-paste prompts designed for your external AI chatbot. For each task:
1. Copy the exact **AI Chatbot Prompt**.
2. Paste it into your AI chatbot to generate the code.
3. Save the generated code under the specified **Target Filename** in this repository.

---

## Architecture Flow Overview

```
[Employee Question on Slack/Discord]
                 │
                 ▼
[AI Question & Gap Detection Pipeline]
                 │
                 ▼
[Discord "Approve" Button Triggered (Member 2)]
                 │
                 ▼
[Phase 4: doc_pusher_service.py] ──> [Phase 1: SkillPatch Enhancer]
                 │
                 ▼
[Phase 3: notion_pusher.py]
                 │
                 ▼
[Live Notion Knowledge Base / Developer Onboarding Docs]
```

---

## Task 1: SkillPatch Bounty Integration
- **Target Filename:** `skillpatch_integration.py`
- **Purpose:** Standalone script implementing a SkillPatch skill (AI Documentation Summarizer / Gap Formatter) meeting the ₹5,000 bounty criteria.

### Prompt to Copy & Paste into AI Chatbot:
```text
Write a complete, standalone Python module named `skillpatch_integration.py` for the "Silent Onboarding" platform that adheres to the SkillPatch.dev specification to qualify for the bounty category.

Requirements:
1. Implement a clean skill class/handler (e.g., `DocSummarizerSkillPatch` or `DocFormatterSkill`) that takes raw employee Q&A thread text or documentation gap drafts and produces structured, polished Markdown documentation with metadata tags (tags, category, summary, actionable steps).
2. Include standard SkillPatch metadata headers/docstrings (Skill Name, Description, Author, Version, Inputs, Outputs, Tags).
3. Provide robust input validation and fallback handling if an external LLM API key is optional or provided via environment variables (`OPENAI_API_KEY` / `GEMINI_API_KEY` or mock fallback).
4. Include a standalone execution block (`if __name__ == "__main__":`) demonstrating end-to-end execution on sample onboarding Q&A input and printing the formatted Markdown output.
5. Keep the code clean, fully commented, and modular so it can be imported by other services.
```

---

## Task 2: Notion Setup & Environment Configuration
- **Target Filename:** `.env.example` and `notion_config.py`
- **Purpose:** Centralized configuration and validation for Notion integration credentials (`NOTION_API_KEY`, `NOTION_PAGE_ID`, and optional SkillPatch configs).

### Prompt to Copy & Paste into AI Chatbot:
```text
Write two files for configuring the Notion API integration in Python:

1. `.env.example`: A clean environment variable template file containing:
   - `NOTION_API_KEY`: Notion Internal Integration Secret Token (starts with `secret_` or `ntn_`)
   - `NOTION_PAGE_ID`: Target Notion page ID (32-character hex string)
   - `SKILLPATCH_API_KEY`: (Optional)

2. `notion_config.py`: A Python module that:
   - Loads environment variables using `python-dotenv`.
   - Normalizes and formats the 32-character Notion Page ID into UUID format with hyphens (`8-4-4-4-12`) if needed.
   - Validates that required environment variables exist and raises clear, friendly error messages if they are missing.
   - Defines standard Notion API constants (e.g., Notion API Version `2022-06-28`, base URL `https://api.notion.com/v1`).
   - Includes a quick verification function `check_credentials()` to test configuration health.
```

---

## Task 3: The Markdown-to-Notion Pusher
- **Target Filename:** `notion_pusher.py`
- **Purpose:** Core Python script using Notion API to parse Markdown strings and append them as native Notion blocks (headings, paragraphs, bullet points, callouts, code blocks).

### Prompt to Copy & Paste into AI Chatbot:
```text
Write a robust, production-grade Python script named `notion_pusher.py` that takes a Markdown string and appends it as structured native blocks to a specified Notion page using the Notion REST API (`https://api.notion.com/v1/blocks/{page_id}/children`).

Requirements:
1. Support converting key Markdown elements into Notion Block objects:
   - H1 (`# ...`) -> `heading_1`
   - H2 (`## ...`) -> `heading_2`
   - H3 (`### ...`) -> `heading_3`
   - Bulleted list items (`- ...` or `* ...`) -> `bulleted_list_item`
   - Numbered list items (`1. ...`) -> `numbered_list_item`
   - Code blocks (` ```language ... ``` `) -> `code` with language identifier
   - Quotes / Blockquotes (`> ...`) -> `quote` or `callout`
   - Standard text / paragraphs -> `paragraph`
2. Handle rich text formatting (bold `**text**`, italic `*text*`, inline code `` `code` ``) where appropriate or cleanly parse plain text.
3. Notion API limits block appends to 100 blocks per request; implement automatic chunking/batching if block count exceeds 100.
4. Provide a core function `append_markdown_to_notion(page_id: str, markdown_content: str, api_key: str = None) -> bool`.
5. Include a command-line interface / standalone demo mode (`if __name__ == "__main__":`) that reads from `.env` or sample input, appends sample Markdown documentation, and prints the result with Notion API response status.
```

---

## Task 4: Hooking with Member 2 (Discord Approve Callback Bridge)
- **Target Filename:** `doc_pusher_service.py`
- **Purpose:** A callable interface / API function ready to be handed to Member 2 so that clicking "Approve" in Discord directly updates the Notion docs.

### Prompt to Copy & Paste into AI Chatbot:
```text
Write a clean integration service file named `doc_pusher_service.py` that bridges Member 2's Discord Bot "Approve" action with the Notion Pusher and SkillPatch pipelines.

Requirements:
1. Create an asynchronous/synchronous handler function `handle_approval_event(title: str, content: str, author: str = "AI Assistant", tags: list = None) -> dict`.
2. Flow inside the function:
   a. Optional: Pass content through `SkillPatch` enhancer/formatter (from `skillpatch_integration.py`) to ensure high quality documentation structure.
   b. Add header metadata (e.g. "Approved via Discord Onboarding Review by {author} on {timestamp}").
   c. Call `append_markdown_to_notion` from `notion_pusher.py` to push to the live Notion workspace.
   d. Return a structured result dictionary with status (`"success"` / `"error"`), Notion page URL or block IDs, and error messages if any.
3. Provide an optional lightweight FastAPI/Flask webhook endpoint (`POST /api/approve-doc`) so Member 2's bot can either import this module directly or trigger it via HTTP POST.
4. Include mock test execution in `if __name__ == "__main__":` simulating a Discord bot approval event.
```

---

## Task 5: End-to-End Verification Pipeline
- **Target Filename:** `test_pipeline.py`
- **Purpose:** Full end-to-end test script to verify that credentials, SkillPatch formatting, and Notion live page updates work seamlessly.

### Prompt to Copy & Paste into AI Chatbot:
```text
Write an end-to-end automated testing script named `test_pipeline.py` for the Silent Onboarding integration stack.

Requirements:
1. Verify loading of environment variables from `.env`.
2. Test Notion API connectivity and permissions (verify the page is accessible with the integration token).
3. Test SkillPatch skill formatting on sample employee Q&A context:
   - Question: "Where do I get the staging database credentials?"
   - Resolution: "Mail the database administrator or check 1Password vault 'Dev-Staging'."
4. Test pushing the generated documentation to the live Notion page.
5. Print a comprehensive status report showing checkmarks for:
   - [x] Environment & Notion Credentials Valid
   - [x] SkillPatch ₹5,000 Bounty Skill Execution
   - [x] Notion Block Serialization & Upload
   - [x] Discord Approval Webhook Ready
```
