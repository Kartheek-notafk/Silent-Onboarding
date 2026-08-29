"""
Documentation Pusher Service & Discord Bot Callback Bridge
Silent Onboarding Pipeline

This module is the integration point for Member 2's Discord Bot.
When a reviewer clicks the "Approve" button on a proposed documentation draft,
this service formats the approved doc and pushes it directly to the live Notion workspace.
"""

import os
import sys
from pathlib import Path

# Ensure current directory is in sys.path
current_dir = str(Path(__file__).resolve().parent)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Import internal modules
from notion_pusher import append_markdown_to_notion, verify_notion_page_access
from notion_config import get_notion_page_id
from skillpatch_integration import DocSummarizerSkillPatch

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] (DocPusherService) %(message)s')
logger = logging.getLogger("doc_pusher_service")


def format_approved_markdown(
    title: str,
    content: str,
    reviewer: str = "Admin Reviewer",
    source_question: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> str:
    """
    Wraps the approved documentation draft with an official verification banner,
    metadata tags, timestamp, and source context.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    tag_str = ", ".join(tags) if tags else "onboarding, verified-doc"
    
    header_block = f"""---
title: {title}
approved_by: {reviewer}
timestamp: {now_str}
tags: [{tag_str}]
status: live
---

# {title}

> [!NOTE]
> 🚀 **Verified & Published via Silent Onboarding Discord Approval**
> * **Reviewer:** @{reviewer}
> * **Approved at:** {now_str}
"""
    if source_question:
        header_block += f"> * **Originating Query:** \"{source_question}\"\n"

    header_block += "\n---\n\n"
    return header_block + content.strip() + "\n"


def publish_approved_doc(
    title: str,
    markdown_content: str,
    reviewer: str = "Discord Reviewer",
    source_question: Optional[str] = None,
    tags: Optional[List[str]] = None,
    page_id: Optional[str] = None,
    use_skillpatch: bool = False
) -> Dict[str, Any]:
    """
    Primary callable function for Member 2's Discord Bot.
    
    Args:
        title (str): Title of the documentation entry.
        markdown_content (str): The documentation draft or raw Q&A context.
        reviewer (str): Username/ID of the approver on Discord.
        source_question (str, optional): The original employee question.
        tags (list, optional): Metadata tags for categorization.
        page_id (str, optional): Notion Page ID (defaults to environment).
        use_skillpatch (bool): Whether to pass through SkillPatch enhancer first.
        
    Returns:
        Dict: JSON response with status, blocks added, and Notion live URL.
    """
    logger.info(f"Received approval event for doc '{title}' approved by '{reviewer}'")
    
    final_content = markdown_content
    
    # Optional SkillPatch refinement
    if use_skillpatch:
        try:
            logger.info("Passing draft through SkillPatch summarizer...")
            skill = DocSummarizerSkillPatch()
            final_content = skill.process(markdown_content)
        except Exception as e:
            logger.warning(f"SkillPatch preprocessing warning: {e}. Proceeding with raw draft.")

    # Format document with metadata banner
    formatted_markdown = format_approved_markdown(
        title=title,
        content=final_content,
        reviewer=reviewer,
        source_question=source_question,
        tags=tags
    )

    # Push to Notion page
    target_page = page_id or get_notion_page_id()
    result = append_markdown_to_notion(
        markdown_content=formatted_markdown,
        page_id=target_page
    )

    if result.get("success"):
        logger.info(f"Document successfully published to Notion! Page: {result.get('notion_url')}")
    else:
        logger.error(f"Failed to publish document to Notion: {result.get('error')}")

    return {
        "status": "success" if result.get("success") else "error",
        "title": title,
        "reviewer": reviewer,
        "details": result
    }


# ==============================================================================
# Lightweight HTTP Webhook Server (Alternative trigger for Member 2)
# ==============================================================================

class WebhookRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP Server handling POST /api/approve-doc requests from Discord Bot.
    """
    def do_POST(self):
        if self.path in ("/api/approve-doc", "/webhook/approve"):
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                payload = json.loads(post_data.decode('utf-8'))
                
                title = payload.get("title", "New Onboarding Guide")
                content = payload.get("content", "")
                reviewer = payload.get("reviewer", "Discord Bot")
                source_question = payload.get("source_question")
                tags = payload.get("tags", [])
                page_id = payload.get("page_id")
                use_skillpatch = payload.get("use_skillpatch", False)

                if not content:
                    self._send_response(400, {"error": "Missing 'content' in request body."})
                    return

                res = publish_approved_doc(
                    title=title,
                    markdown_content=content,
                    reviewer=reviewer,
                    source_question=source_question,
                    tags=tags,
                    page_id=page_id,
                    use_skillpatch=use_skillpatch
                )
                self._send_response(200 if res["status"] == "success" else 500, res)
                
            except Exception as e:
                self._send_response(500, {"error": f"Server processing error: {str(e)}"})
        else:
            self._send_response(404, {"error": "Endpoint not found. Use POST /api/approve-doc"})

    def do_GET(self):
        if self.path == "/health":
            self._send_response(200, {"status": "healthy", "service": "doc_pusher_service"})
        else:
            self._send_response(200, {
                "message": "Silent Onboarding Doc Pusher Service is running.",
                "endpoints": {
                    "POST /api/approve-doc": "Trigger Notion doc publish from Discord Approve button",
                    "GET /health": "Health check"
                }
            })

    def _send_response(self, code: int, body: dict):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2).encode('utf-8'))

    def log_message(self, format, *args):
        # Clean logging
        logger.info(f"HTTP {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


def start_webhook_server(port: int = 8000, blocking: bool = True):
    """Starts the HTTP webhook listener."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, WebhookRequestHandler)
    logger.info(f"Webhook server started at http://localhost:{port}/")
    logger.info(f"Member 2 can trigger POST http://localhost:{port}/api/approve-doc")
    
    if blocking:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down webhook server...")
            httpd.server_close()
    else:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd


if __name__ == "__main__":
    print("=" * 60)
    print("  Silent Onboarding -- Discord Approval Service Demo")
    print("=" * 60)
    
    # Demonstration of programmatic call that Member 2 will execute
    mock_discord_title = "Database & Server Credentials Access Guide"
    mock_discord_content = """## Database Setup
To connect to the staging database:
1. Open your terminal or database GUI.
2. Enter host `staging-db.internal.corp`.
3. Fetch your password from the team 1Password vault.

## Support
For urgent queries, contact `@dba-admin` on Slack `#support`.
"""
    
    print("\nSimulating Discord Bot 'Approve' Button Click Interaction...")
    result = publish_approved_doc(
        title=mock_discord_title,
        markdown_content=mock_discord_content,
        reviewer="sathwik#0001",
        source_question="Where do I get the staging database credentials?",
        tags=["database", "staging", "onboarding"]
    )
    
    print("\nApproval Dispatch Response:")
    print(json.dumps(result, indent=2))
    print("=" * 60)
