import sys
import os
from dotenv import load_dotenv

# Add parent directory to sys.path so we can import from notion_API
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from notion_API.notion_pusher import append_markdown_to_notion
from notion_API.notion_config import get_notion_api_key, get_notion_page_id

load_dotenv()

def sync_to_notion(draft_id: int, content: str) -> bool:
    """
    Calls Member 3's robust Notion API parser to sync the draft to the live workspace.
    """
    print(f"[Notion Integration] Exporting approved draft #{draft_id} to Notion...")
    
    api_key = get_notion_api_key()
    page_id = get_notion_page_id()
    
    if not api_key or not page_id:
        print("[Notion Integration Error] Missing Notion API Key or Page ID in .env")
        return False
        
    try:
        # Title of the page is the first line or a default
        title = f"AI Documentation Draft #{draft_id}"
        result = append_markdown_to_notion(page_id=page_id, markdown_content=content, api_key=api_key)
        
        if isinstance(result, dict) and result.get("success"):
            print(f"[Notion Integration] Successfully synced draft #{draft_id} to Notion!")
            return True
        else:
            error_msg = result.get("error", "Unknown Error") if isinstance(result, dict) else "Unknown return type"
            print(f"[Notion Integration Error] Failed to sync draft #{draft_id} to Notion. Error: {error_msg}")
            return False
    except Exception as e:
        print(f"[Notion Integration Error] Exception during Notion sync: {e}")
        return False
