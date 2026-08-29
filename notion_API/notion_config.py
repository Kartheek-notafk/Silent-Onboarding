"""
Notion Integration Configuration & Credentials Helper
Silent Onboarding Pipeline
"""

import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure stdout handles unicode if possible
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Automatically locate and load .env file from project directory
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()  # Default search

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


def clean_notion_page_id(page_input: str) -> str:
    """
    Extracts and standardizes a 32-character hexadecimal Notion Page ID
    from raw IDs, hyphenated UUIDs, or full Notion URLs.
    
    Examples:
        - "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d" -> "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
        - "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d" -> "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
        - "https://www.notion.so/workspace/Doc-Title-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d" -> "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    """
    if not page_input:
        return ""
    
    # Strip URL queries / parameters (e.g. ?pvs=4)
    page_input = page_input.split("?")[0].strip()
    
    # Match any 32 continuous hex characters (even at the end of a slug)
    hex_match = re.findall(r"[0-9a-fA-F]{32}", page_input.replace("-", ""))
    if hex_match:
        raw_hex = hex_match[-1]
        # Format as standard UUID 8-4-4-4-12
        return f"{raw_hex[0:8]}-{raw_hex[8:12]}-{raw_hex[12:16]}-{raw_hex[16:20]}-{raw_hex[20:32]}"
    
    # Fallback to standard hyphenated UUID matching
    uuid_match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", page_input)
    if uuid_match:
        return uuid_match.group(0)
    
    return page_input.strip()


def get_notion_api_key() -> str:
    """Returns the configured Notion integration API token."""
    return os.environ.get("NOTION_API_KEY", "").strip()


def get_notion_page_id() -> str:
    """Returns the normalized Notion target page ID."""
    raw_id = os.environ.get("NOTION_PAGE_ID", "").strip()
    return clean_notion_page_id(raw_id)


def get_notion_headers(api_key: str = None) -> dict:
    """Returns the authorization and version headers required by the Notion REST API."""
    token = api_key or get_notion_api_key()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


def validate_config(raise_error: bool = False) -> tuple[bool, str]:
    """
    Checks if all required environment variables are set and formatted properly.
    """
    api_key = get_notion_api_key()
    page_id = get_notion_page_id()
    
    errors = []
    if not api_key:
        errors.append("Missing NOTION_API_KEY. Create an integration at https://www.notion.so/my-integrations")
    elif not (api_key.startswith("secret_") or api_key.startswith("ntn_")):
        errors.append("NOTION_API_KEY usually starts with 'secret_' or 'ntn_'. Please verify your secret token.")
        
    if not page_id:
        errors.append("Missing NOTION_PAGE_ID. Set NOTION_PAGE_ID in your .env file or environment.")
        
    if errors:
        msg = "\n".join(f"[!] {e}" for e in errors)
        if raise_error:
            raise ValueError(msg)
        return False, msg
    
    return True, "[OK] Notion credentials & Page ID are properly configured."


def check_credentials():
    """Prints a diagnostic view of current configuration status."""
    print("=" * 60)
    print("  Silent Onboarding -- Notion Configuration Status")
    print("=" * 60)
    
    api_key = get_notion_api_key()
    page_id = get_notion_page_id()
    
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else ("(Not Set)" if not api_key else "******")
    
    print(f"* Notion API Key : {masked_key}")
    print(f"* Notion Page ID : {page_id if page_id else '(Not Set)'}")
    print(f"* Notion Version : {NOTION_API_VERSION}")
    print(f"* API Base URL   : {NOTION_BASE_URL}")
    print("-" * 60)
    
    is_valid, message = validate_config()
    print(message)
    print("=" * 60)
    return is_valid


if __name__ == "__main__":
    check_credentials()
