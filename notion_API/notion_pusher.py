"""
Notion Pusher Module — Silent Onboarding
Converts Markdown documentation drafts into native Notion blocks
and appends them to a live Notion workspace page via Notion REST API.
"""

import os
import re
import sys
import json
import logging
import requests
from typing import List, Dict, Any, Optional

from .notion_config import (
    clean_notion_page_id,
    get_notion_api_key,
    get_notion_page_id,
    get_notion_headers,
    NOTION_BASE_URL,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("notion_pusher")

# Maximum characters per text block chunk in Notion API
MAX_TEXT_LENGTH = 2000
# Maximum blocks per single append request in Notion API
MAX_BLOCKS_PER_REQUEST = 100


def parse_inline_rich_text(text: str) -> List[Dict[str, Any]]:
    """
    Parses Markdown inline styling (bold, italic, code, links) into Notion rich_text objects.
    """
    if not text:
        return []

    # If text is too long, slice into 2000-char pieces
    if len(text) > MAX_TEXT_LENGTH:
        chunks = [text[i:i + MAX_TEXT_LENGTH] for i in range(0, len(text), MAX_TEXT_LENGTH)]
        result = []
        for c in chunks:
            result.extend(parse_inline_rich_text(c))
        return result

    rich_texts = []
    
    # Regex to match links [text](url), bold **text**, code `text`, and italic *text*
    pattern = re.compile(
        r'(\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^\)]+)\))|'
        r'(\*\*(?P<bold_text>.+?)\*\*)|'
        r'(`(?P<code_text>[^`]+)`)|'
        r'(\*(?P<italic_text>.+?)\*)'
    )
    
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        # Preceding normal text
        if start > last_idx:
            normal_chunk = text[last_idx:start]
            rich_texts.append({
                "type": "text",
                "text": {"content": normal_chunk},
                "annotations": {"bold": False, "italic": False, "code": False, "color": "default"}
            })
            
        gd = match.groupdict()
        if gd.get("link_text"):
            rich_texts.append({
                "type": "text",
                "text": {"content": gd["link_text"], "link": {"url": gd["link_url"]}},
                "annotations": {"bold": False, "italic": False, "code": False, "color": "default"}
            })
        elif gd.get("bold_text"):
            rich_texts.append({
                "type": "text",
                "text": {"content": gd["bold_text"]},
                "annotations": {"bold": True, "italic": False, "code": False, "color": "default"}
            })
        elif gd.get("code_text"):
            rich_texts.append({
                "type": "text",
                "text": {"content": gd["code_text"]},
                "annotations": {"bold": False, "italic": False, "code": True, "color": "default"}
            })
        elif gd.get("italic_text"):
            rich_texts.append({
                "type": "text",
                "text": {"content": gd["italic_text"]},
                "annotations": {"bold": False, "italic": True, "code": False, "color": "default"}
            })
        last_idx = end

    # Trailing normal text
    if last_idx < len(text):
        rich_texts.append({
            "type": "text",
            "text": {"content": text[last_idx:]},
            "annotations": {"bold": False, "italic": False, "code": False, "color": "default"}
        })

    return rich_texts if rich_texts else [{
        "type": "text",
        "text": {"content": text},
        "annotations": {"bold": False, "italic": False, "code": False, "color": "default"}
    }]


def create_notion_block(block_type: str, content: str, extra: dict = None) -> Dict[str, Any]:
    """Helper to construct a single Notion block object."""
    rich_text = parse_inline_rich_text(content)
    
    if block_type in ("heading_1", "heading_2", "heading_3", "paragraph", "bulleted_list_item", "numbered_list_item", "quote"):
        payload = {"rich_text": rich_text}
        if extra:
            payload.update(extra)
        return {
            "object": "block",
            "type": block_type,
            block_type: payload
        }
    
    elif block_type == "to_do":
        checked = extra.get("checked", False) if extra else False
        return {
            "object": "block",
            "type": "to_do",
            "to_do": {
                "rich_text": rich_text,
                "checked": checked
            }
        }
        
    elif block_type == "code":
        language = (extra.get("language") or "plain text").lower()
        # Supported Notion languages mapping
        valid_languages = [
            "python", "javascript", "typescript", "json", "html", "css", "bash",
            "shell", "markdown", "sql", "java", "c", "cpp", "c#", "go", "rust",
            "yaml", "dockerfile", "plain text"
        ]
        if language not in valid_languages:
            language = "plain text"
            
        return {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": content[:MAX_TEXT_LENGTH]}}],
                "language": language
            }
        }
        
    elif block_type == "callout":
        emoji = extra.get("emoji", "💡") if extra else "💡"
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": rich_text,
                "icon": {"type": "emoji", "emoji": emoji}
            }
        }
        
    elif block_type == "divider":
        return {
            "object": "block",
            "type": "divider",
            "divider": {}
        }
        
    # Default fallback
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text}
    }


def markdown_to_notion_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Parses a complete Markdown string into an array of Notion block objects.
    """
    blocks = []
    lines = markdown_text.splitlines()
    
    in_code_block = False
    code_buffer = []
    code_language = "plain text"
    
    in_frontmatter = False
    frontmatter_count = 0
    frontmatter_lines = []

    for line in lines:
        stripped = line.strip()
        
        # Handle YAML frontmatter (--- ... ---)
        if stripped == "---" and (frontmatter_count == 0 or in_frontmatter):
            frontmatter_count += 1
            if frontmatter_count == 1:
                in_frontmatter = True
                continue
            elif frontmatter_count == 2:
                in_frontmatter = False
                # Convert frontmatter to a Notion callout metadata card
                if frontmatter_lines:
                    meta_text = " ℹ️  Metadata:\n" + "\n".join(frontmatter_lines)
                    blocks.append(create_notion_block("callout", meta_text, {"emoji": "📌"}))
                continue
                
        if in_frontmatter:
            frontmatter_lines.append(stripped)
            continue

        # Handle Code Fences
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_language = stripped[3:].strip() or "plain text"
                code_buffer = []
            else:
                in_code_block = False
                code_content = "\n".join(code_buffer)
                blocks.append(create_notion_block("code", code_content, {"language": code_language}))
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        # Skip empty lines
        if not stripped:
            continue

        # Dividers
        if stripped in ("---", "***", "___"):
            blocks.append(create_notion_block("divider", ""))
            continue

        # Headings
        if stripped.startswith("### "):
            blocks.append(create_notion_block("heading_3", stripped[4:]))
        elif stripped.startswith("## "):
            blocks.append(create_notion_block("heading_2", stripped[3:]))
        elif stripped.startswith("# "):
            blocks.append(create_notion_block("heading_1", stripped[2:]))

        # Checkboxes / To-Do
        elif re.match(r"^-\s*\[\s*\]\s+", stripped):
            content = re.sub(r"^-\s*\[\s*\]\s+", "", stripped)
            blocks.append(create_notion_block("to_do", content, {"checked": False}))
        elif re.match(r"^-\s*\[x\]\s+", stripped, re.IGNORECASE):
            content = re.sub(r"^-\s*\[x\]\s+", "", stripped, flags=re.IGNORECASE)
            blocks.append(create_notion_block("to_do", content, {"checked": True}))

        # Bulleted Lists
        elif re.match(r"^[\*\-\+]\s+", stripped):
            content = re.sub(r"^[\*\-\+]\s+", "", stripped)
            blocks.append(create_notion_block("bulleted_list_item", content))

        # Numbered Lists
        elif re.match(r"^\d+\.\s+", stripped):
            content = re.sub(r"^\d+\.\s+", "", stripped)
            blocks.append(create_notion_block("numbered_list_item", content))

        # Quotes and Callouts
        elif stripped.startswith("> "):
            quote_text = stripped[2:].strip()
            if quote_text.startswith("[!NOTE]") or quote_text.startswith("[!TIP]") or quote_text.startswith("[!IMPORTANT]"):
                blocks.append(create_notion_block("callout", quote_text, {"emoji": "💡"}))
            else:
                blocks.append(create_notion_block("quote", quote_text))

        # Standard Paragraph
        else:
            blocks.append(create_notion_block("paragraph", stripped))

    # Catch unclosed code blocks
    if in_code_block and code_buffer:
        code_content = "\n".join(code_buffer)
        blocks.append(create_notion_block("code", code_content, {"language": code_language}))

    return blocks


def verify_notion_page_access(page_id: str = None, api_key: str = None) -> Dict[str, Any]:
    """
    Checks whether the target Notion page exists and is accessible
    by the configured Notion integration.
    """
    clean_id = clean_notion_page_id(page_id or get_notion_page_id())
    if not clean_id:
        return {"success": False, "error": "No Notion Page ID provided or configured."}

    url = f"{NOTION_BASE_URL}/pages/{clean_id}"
    headers = get_notion_headers(api_key)

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            title = "(Untitled)"
            # Extract page title property if available
            props = data.get("properties", {})
            for p in props.values():
                if p.get("type") == "title":
                    title_objs = p.get("title", [])
                    if title_objs:
                        title = "".join(t.get("plain_text", "") for t in title_objs)
            return {
                "success": True,
                "page_id": clean_id,
                "page_title": title,
                "url": data.get("url", f"https://www.notion.so/{clean_id.replace('-', '')}")
            }
        elif response.status_code == 404:
            return {
                "success": False,
                "error": "Page not found (HTTP 404). Ensure you clicked '...' on your Notion page -> 'Connect to' / 'Add connection' -> selected your integration."
            }
        elif response.status_code == 401:
            return {"success": False, "error": "Invalid or unauthorized NOTION_API_KEY (HTTP 401)."}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "error": f"Connection error: {str(e)}"}


def append_markdown_to_notion(
    markdown_content: str,
    page_id: str = None,
    api_key: str = None
) -> Dict[str, Any]:
    """
    Main function to append a Markdown string as native Notion blocks to a Notion page.
    
    Args:
        markdown_content: Markdown formatted text.
        page_id: Target Notion page ID (optional if set in environment).
        api_key: Notion Integration token (optional if set in environment).
        
    Returns:
        Dict with status, number of blocks added, and response details.
    """
    clean_id = clean_notion_page_id(page_id or get_notion_page_id())
    if not clean_id:
        return {"success": False, "error": "NOTION_PAGE_ID is missing. Please set it in .env or pass page_id."}

    headers = get_notion_headers(api_key)
    if not headers.get("Authorization") or headers["Authorization"] == "Bearer ":
        return {"success": False, "error": "NOTION_API_KEY is missing. Please set it in .env or pass api_key."}

    blocks = markdown_to_notion_blocks(markdown_content)
    if not blocks:
        return {"success": False, "error": "No valid blocks generated from input Markdown."}

    logger.info(f"Parsed Markdown into {len(blocks)} Notion block(s). Appending to page {clean_id}...")

    # Batch append requests in groups of MAX_BLOCKS_PER_REQUEST (100)
    total_added = 0
    created_block_ids = []
    
    for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
        chunk = blocks[i:i + MAX_BLOCKS_PER_REQUEST]
        url = f"{NOTION_BASE_URL}/blocks/{clean_id}/children"
        payload = {"children": chunk}

        try:
            response = requests.patch(url, headers=headers, json=payload, timeout=20)
            if response.status_code in (200, 201):
                data = response.json()
                results = data.get("results", [])
                total_added += len(results)
                created_block_ids.extend([b.get("id") for b in results if b.get("id")])
            elif response.status_code == 404:
                return {
                    "success": False,
                    "error": f"Page {clean_id} not found or not shared with integration. Click page '...' -> Connect to -> Select your integration."
                }
            else:
                return {
                    "success": False,
                    "error": f"Notion API error (HTTP {response.status_code}): {response.text}"
                }
        except Exception as e:
            return {"success": False, "error": f"Failed to send request to Notion: {str(e)}"}

    logger.info(f"Successfully appended {total_added} blocks to Notion page!")
    return {
        "success": True,
        "page_id": clean_id,
        "blocks_added": total_added,
        "block_ids": created_block_ids,
        "notion_url": f"https://www.notion.so/{clean_id.replace('-', '')}"
    }


if __name__ == "__main__":
    print("=" * 60)
    print("  Silent Onboarding — Notion Pusher Standalone Demo")
    print("=" * 60)

    sample_doc = """---
title: Staging Database Access & Credentials
category: Engineering Infrastructure
tags: [database, staging, mysql, credentials]
summary: Procedure for acquiring secure access to the staging database instance.
---

# Staging Database Setup & Access Guide

## Overview
New developers frequently inquire about staging database access. This guide documents the standardized self-service and approval workflow.

> [!IMPORTANT]
> Never share database passwords over unencrypted Slack channels. All credentials are vault-managed.

## Step-by-Step Instructions
1. **Access 1Password Vault:** Navigate to the `Engineering - Staging` shared vault.
2. **Retrieve Connection String:** Look for item `mysql-staging-replica-01`.
3. **Connect via CLI / Client:**
```bash
mysql -h staging-db.internal.corp -u dev_user -p --database=onboarding_staging
```

## Need Elevated Permissions?
- [ ] Ping `@dba-oncall` in `#dev-support`
- [ ] Attach your Jira onboarding ticket ID
- [ ] Confirm compliance training completed
"""

    print("Checking Notion Page configuration...")
    access_check = verify_notion_page_access()
    print(f"Page Access Status: {access_check}")

    if access_check.get("success"):
        print("\nUploading sample documentation to Notion...")
        result = append_markdown_to_notion(sample_doc)
        print(f"Result: {json.dumps(result, indent=2)}")
    else:
        print("\nNote: Live upload skipped because Notion credentials are not yet set in .env.")
        print("To push live docs, add your NOTION_API_KEY and NOTION_PAGE_ID to .env")
        print("\nLocal Markdown-to-Blocks parser verification:")
        blocks = markdown_to_notion_blocks(sample_doc)
        print(f"[OK] Successfully converted sample doc into {len(blocks)} Notion block objects!")
