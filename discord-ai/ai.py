import os
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

from models import KeywordTracker

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "can't", "cannot",
    "could", "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
    "yourselves", "hi", "hello", "hey", "thanks", "ok", "please", "help"
}

def extract_and_update_keywords(content: str, db_session) -> Dict[str, int]:
    """
    Extracts tech and onboarding keywords from message content,
    increments their frequency count persistently in the KeywordTracker table.
    """
    if not content:
        return {}
        
    words = re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', content.lower())
    updated_counts = {}
    
    for word in set(words):
        if word in STOPWORDS or word.isdigit():
            continue
            
        record = db_session.query(KeywordTracker).filter(KeywordTracker.keyword == word).first()
        if record:
            record.count += 1
            record.last_updated = datetime.utcnow()
        else:
            record = KeywordTracker(keyword=word, count=1, last_updated=datetime.utcnow())
            db_session.add(record)
            
        updated_counts[word] = record.count
        
    db_session.commit()
    return updated_counts

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

def clean_markdown_formatting(text: str) -> str:
    """
    Strips unnecessary ugly markdown syntax such as bold (**), headers (#, ##, ###),
    and code block markers to produce clean, readable text without ugly formatting.
    """
    if not text:
        return ""
    # Remove headers (#, ##, ### at line starts)
    text = re.sub(r'^[ \t]*#+[ \t]*', '', text, flags=re.MULTILINE)
    # Remove bold/italic delimiters (**text**, *text*, __text__, _text_)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    # Remove multi-line code block markers (```)
    text = re.sub(r'```[a-zA-Z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    return text.strip()

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

def analyze_messages_and_generate_draft(messages: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Uses Gemini AI model to analyze onboarding channel messages, determine if there are
    recurrent questions/issues requiring documentation changes, and format a documentation draft.
    Returns a dictionary containing:
    - content: summary description of the proposal
    - priority: High, Medium, or Low based on issue severity and frequency
    - target_section: section in docs being modified
    - proposed_change: exact documentation updates
    """
    if not messages:
        return None

    formatted_messages = "\n".join([f"- [{m.get('user', 'User')}]: {m.get('content', '')}" for m in messages])
    kb_context = get_knowledge_base_context()

    if client:
        try:
            prompt = f"""
You are an expert AI Technical Writer analyzing recent discussion messages from a team's #onboarding-help Discord channel.

Current Project Knowledge Base:
{kb_context}

Recent Channel Messages:
{formatted_messages}

Task Instructions:
1. Determine if the messages contain questions, friction, setup issues, or missing documentation topics.
2. If the messages are purely casual chatter (e.g. "hi", "thanks", "ok", emojis) with NO documentation-relevant issues, reply ONLY with "NO_DOC_CHANGES_NEEDED".
3. Otherwise:
   - Assign a Priority Level: "High" (blocking errors, missing core setup steps, multiple users affected), "Medium" (common questions, minor clarity improvements), or "Low" (nice-to-have tips).
   - Identify Target Section in documentation to update (e.g., Environment Setup, Discord Bot Setup, Database Configuration).
   - Draft Proposed Documentation Update (clean instructions to be merged into the knowledge base).
   - Explain Rationale/Summary based on user messages.

Do NOT use ugly markdown syntax like **, ##, ###, or code fence wrappers in the response.

Format response clearly as:
PRIORITY: [High/Medium/Low]
TARGET SECTION: [Section Name]
PROPOSED UPDATE:
[Clean text update to append/update in docs]
RATIONALE:
[Summary of why this update is proposed]
"""
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            output_text = response.text.strip()
            if "NO_DOC_CHANGES_NEEDED" in output_text:
                return None

            priority = "Medium"
            target_section = "Common Onboarding Issues & Troubleshooting"
            proposed_change = output_text
            rationale = output_text

            p_match = re.search(r'PRIORITY:\s*(High|Medium|Low)', output_text, re.IGNORECASE)
            if p_match:
                priority = p_match.group(1).capitalize()

            t_match = re.search(r'TARGET SECTION:\s*(.*?)(?=\n[A-Z\s]+:|$)', output_text, re.DOTALL)
            if t_match:
                target_section = t_match.group(1).strip()

            u_match = re.search(r'PROPOSED UPDATE:\s*(.*?)(?=\nRATIONALE:|$)', output_text, re.DOTALL)
            if u_match:
                proposed_change = u_match.group(1).strip()

            r_match = re.search(r'RATIONALE:\s*(.*)', output_text, re.DOTALL)
            if r_match:
                rationale = r_match.group(1).strip()

            clean_proposed = clean_markdown_formatting(proposed_change)
            clean_summary = clean_markdown_formatting(rationale)

            full_content = f"Priority: {priority}\nTarget Section: {target_section}\n\nProposed Update:\n{clean_proposed}\n\nRationale:\n{clean_summary}"

            return {
                "content": full_content,
                "priority": priority,
                "target_section": target_section,
                "proposed_change": clean_proposed
            }
        except Exception as e:
            print(f"[Gemini AI Error] Failed to generate proposal: {e}")

    # Fallback if GEMINI_API_KEY is not configured
    keywords = ["python", "venv", "pip", "discord", "token", "error", "fastapi", "db", "issue", "how"]
    has_relevant = any(any(kw in m.get("content", "").lower() for kw in keywords) for m in messages)
    if not has_relevant:
        return None

    # Calculate fallback priority based on error presence
    has_error = any("error" in m.get("content", "").lower() or "failed" in m.get("content", "").lower() for m in messages)
    priority = "High" if has_error else "Medium"
    target_section = "Common Onboarding Issues & Troubleshooting"
    proposed_change = "Add troubleshooting guidelines for python virtual environment activation and dependency setup."
    full_content = f"Priority: {priority}\nTarget Section: {target_section}\n\nProposed Update:\n{proposed_change}\n\nRationale:\nUsers reported setup questions in the onboarding channel."

    return {
        "content": full_content,
        "priority": priority,
        "target_section": target_section,
        "proposed_change": proposed_change
    }

def answer_onboarding_question(question: str) -> str:
    """
    Uses Gemini AI model grounded on the knowledge base to answer onboarding & setup questions directly.
    Formatting is kept clean without ugly markdown tags.
    """
    kb_context = get_knowledge_base_context()

    if client:
        try:
            prompt = f"""
You are an intelligent Onboarding AI Assistant for a software engineering project.

Project Knowledge Base:
{kb_context}

User Question:
"{question}"

Task Instructions:
- Provide a helpful, clear, and direct answer based on the knowledge base.
- Specifically mention where in the documentation (docs/onboarding_knowledge_base.md) or project files the user can find more details or fix their issue.
- Keep the response concise and friendly.
- Do NOT use ugly markdown syntax like **, ##, ###, or code fence wrappers.
"""
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            raw_answer = response.text.strip()
            return clean_markdown_formatting(raw_answer)
        except Exception as e:
            print(f"[Gemini AI Error] Failed to generate onboarding answer: {e}")

    # Fallback response without ugly markdown
    return (
        f"Onboarding AI Assistant:\n"
        f"Regarding your question: \"{question}\"\n"
        f"Please check docs/onboarding_knowledge_base.md for full environment setup details.\n"
    )

def apply_draft_to_docs(draft_content: str, target_section: Optional[str] = None, proposed_change: Optional[str] = None, admin_notes: Optional[str] = None) -> bool:
    """
    Updates the docs/onboarding_knowledge_base.md file once a draft is approved by the admin.
    """
    kb_path = os.path.join(os.path.dirname(__file__), "docs", "onboarding_knowledge_base.md")
    try:
        content_to_add = proposed_change if proposed_change else draft_content
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        section_title = target_section if target_section else "General Troubleshooting & Updates"
        
        entry = f"\n\n### Section: {section_title} (Admin Approved: {timestamp})\n"
        entry += f"{clean_markdown_formatting(content_to_add)}\n"
        if admin_notes:
            entry += f"Admin Note/Correction: {clean_markdown_formatting(admin_notes)}\n"
            
        with open(kb_path, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"[Docs Update] Applied approved draft changes to {kb_path}")
        return True
    except Exception as e:
        print(f"[Docs Update Error] Failed to update docs file: {e}")
        return False

def search_knowledge_base(query: str) -> str:
    """
    Searches the onboarding knowledge base for matching text and returns clean snippets.
    """
    kb_path = os.path.join(os.path.dirname(__file__), "docs", "onboarding_knowledge_base.md")
    if not os.path.exists(kb_path):
        return "Knowledge base documentation file not found."
        
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        lines = content.split("\n")
        query_lower = query.lower()
        matching_blocks = []
        
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                context_block = "\n".join(lines[start:end])
                matching_blocks.append(context_block)
                
        if matching_blocks:
            results = "\n---\n".join(matching_blocks[:3])
            return clean_markdown_formatting(f"Found matches for '{query}':\n\n{results}")
        else:
            return f"No direct documentation matches found for '{query}'. Ask a question in onboarding-help for AI assistance!"
    except Exception as e:
        return f"Error searching knowledge base: {e}"
