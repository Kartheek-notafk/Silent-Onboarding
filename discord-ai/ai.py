import os
import re
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("[AI Module] Gemini AI client initialized successfully.")
    except Exception as e:
        print(f"[AI Module Error] Failed to initialize Gemini client: {e}")

def get_knowledge_base_context() -> str:
    """Loads knowledge base markdown file for grounding AI responses."""
    kb_path = os.path.join(os.path.dirname(__file__), "docs", "onboarding_knowledge_base.md")
    if os.path.exists(kb_path):
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return "Onboarding Knowledge Base: Python 3.10+, Virtualenv, SQLite app.db, FastAPI, Discord Bot setup."

def analyze_messages_and_generate_draft(messages: List[Dict[str, str]]) -> Optional[str]:
    """
    Uses Gemini AI model to analyze onboarding channel messages, determine if there are
    recurrent questions/issues requiring documentation changes, and format a documentation draft.
    """
    if not messages:
        return None

    formatted_messages = "\n".join([f"- [{m.get('user', 'User')}]: {m.get('content', '')}" for m in messages])
    kb_context = get_knowledge_base_context()

    if client:
        try:
            prompt = f"""
You are an expert AI Technical Writer analyzing recent discussion messages from a team's #onboarding-help Discord channel.

**Current Project Knowledge Base:**
{kb_context}

**Recent Channel Messages:**
{formatted_messages}

**Task Instructions:**
1. Determine if the messages contain questions, friction, setup issues, or missing documentation topics.
2. If the messages are purely casual chatter (e.g. "hi", "thanks", "ok", emojis) with NO documentation-relevant issues, reply ONLY with "NO_DOC_CHANGES_NEEDED".
3. Otherwise, analyze and classify the messages into categories (e.g. Environment Setup, Bot Config, Database/FastAPI).
4. Identify frequently asked questions and user pain points.
5. Suggest concrete markdown documentation updates, including exact sections in the docs where changes should be made.

Output the proposal formatted cleanly in GitHub-flavored Markdown.
"""
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            output_text = response.text.strip()
            if "NO_DOC_CHANGES_NEEDED" in output_text:
                return None
            return output_text
        except Exception as e:
            print(f"[Gemini AI Error] Failed to generate proposal: {e}")

    # Smart Fallback if GEMINI_API_KEY is not configured
    keywords = ["python", "venv", "pip", "discord", "token", "error", "fastapi", "db", "issue", "how"]
    has_relevant = any(any(kw in m.get("content", "").lower() for kw in keywords) for m in messages)
    if not has_relevant:
        return None

    return f"""# 📖 Documentation Update Proposal (AI Analysis)

### Analyzed Messages
{formatted_messages}

### 💡 Suggested Documentation Improvements
- Update `docs/onboarding_knowledge_base.md` with additional troubleshooting details for recent setup questions.
- Note: Configure `GEMINI_API_KEY` in `.env` for full AI generation capabilities.
"""

def answer_onboarding_question(question: str) -> str:
    """
    Uses Gemini AI model grounded on the knowledge base to answer onboarding & setup questions directly.
    """
    kb_context = get_knowledge_base_context()

    if client:
        try:
            prompt = f"""
You are an intelligent Onboarding AI Assistant for a software engineering project.

**Project Knowledge Base:**
{kb_context}

**User Question:**
"{question}"

**Task Instructions:**
- Provide a helpful, clear, and direct answer based on the knowledge base.
- Specifically mention where in the documentation (`docs/onboarding_knowledge_base.md`) or project files the user can find more details or fix their issue.
- Keep the response concise, friendly, and formatted with markdown bullet points.
"""
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            print(f"[Gemini AI Error] Failed to generate onboarding answer: {e}")

    # Fallback response
    return (
        f"🤖 **Onboarding AI Assistant:**\n"
        f"Regarding your question: \"{question}\"\n"
        f"Please check `docs/onboarding_knowledge_base.md` for full environment setup details.\n"
        f"*(Tip: Set `GEMINI_API_KEY` in `.env` to enable dynamic LLM answers!)*"
    )
