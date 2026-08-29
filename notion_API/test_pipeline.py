"""
End-to-End Pipeline Verification Suite
Silent Onboarding — External Integrations & SkillPatch Bounty
"""

import os
import sys
from pathlib import Path

# Ensure local package imports work reliably
current_dir = str(Path(__file__).resolve().parent)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import json
from notion_config import (
    validate_config,
    get_notion_api_key,
    get_notion_page_id,
    clean_notion_page_id,
)
from skillpatch_integration import DocSummarizerSkillPatch
from notion_pusher import (
    markdown_to_notion_blocks,
    verify_notion_page_access,
    append_markdown_to_notion,
)
from doc_pusher_service import publish_approved_doc


def run_pipeline_test():
    print("=" * 70)
    print(" 🚀 SILENT ONBOARDING -- INTEGRATION PIPELINE VERIFICATION")
    print("=" * 70)

    test_results = {}

    # --------------------------------------------------------------------------
    # Step 1: Notion Configuration & Credential Validation
    # --------------------------------------------------------------------------
    print("\n[Step 1/5] Checking Notion Configuration & Environment...")
    is_valid, msg = validate_config()
    api_key = get_notion_api_key()
    page_id = get_notion_page_id()
    
    if is_valid:
        print(f"  [PASS] Notion API credentials loaded successfully.")
        print(f"         Target Page ID: {page_id}")
        test_results["config"] = True
    else:
        print(f"  [INFO] Live credentials not yet set in .env. Running in dry-run mode.")
        print(f"         {msg}")
        test_results["config"] = False

    # --------------------------------------------------------------------------
    # Step 2: SkillPatch Bounty Module Verification
    # --------------------------------------------------------------------------
    print("\n[Step 2/5] Testing SkillPatch Bounty Skill (₹5,000 Category)...")
    sample_qa = """
    Q: Where do I get the staging database credentials?
    A: You'll have to mail the database administrator, they'll give you the further instructions.
    """
    try:
        skill = DocSummarizerSkillPatch()
        skill_output = skill.process(sample_qa)
        assert len(skill_output) > 20, "Output markdown is too short"
        assert "Onboarding" in skill_output or "Guide" in skill_output, "Missing expected headers"
        print("  [PASS] SkillPatch DocSummarizer executed successfully!")
        print("         Generated Structured Markdown Preview:")
        print("         " + "\n         ".join(skill_output.splitlines()[:8]))
        test_results["skillpatch"] = True
    except Exception as e:
        print(f"  [FAIL] SkillPatch execution failed: {e}")
        test_results["skillpatch"] = False

    # --------------------------------------------------------------------------
    # Step 3: Markdown to Notion Block Serialization
    # --------------------------------------------------------------------------
    print("\n[Step 3/5] Testing Markdown -> Notion Block Parser...")
    sample_markdown = """# Database Access Guide
## Overview
Standard procedure for acquiring credentials.

> [!NOTE]
> Database passwords expire every 90 days.

* Request via 1Password
* Message @dba on Slack

```bash
mysql -h staging.db.corp -u dev -p
```
"""
    try:
        blocks = markdown_to_notion_blocks(sample_markdown)
        block_types = [b.get("type") for b in blocks]
        print(f"  [PASS] Successfully parsed {len(blocks)} native Notion blocks:")
        print(f"         Block Types generated: {', '.join(block_types)}")
        test_results["block_parser"] = True
    except Exception as e:
        print(f"  [FAIL] Block parsing failed: {e}")
        test_results["block_parser"] = False

    # --------------------------------------------------------------------------
    # Step 4: Notion Page Access Verification
    # --------------------------------------------------------------------------
    print("\n[Step 4/5] Verifying Live Notion Page Access...")
    if is_valid:
        access_res = verify_notion_page_access(page_id, api_key)
        if access_res.get("success"):
            print(f"  [PASS] Notion Page accessible: '{access_res.get('page_title')}' ({access_res.get('url')})")
            test_results["notion_access"] = True
        else:
            print(f"  [FAIL] Notion Page check failed: {access_res.get('error')}")
            test_results["notion_access"] = False
    else:
        print("  [SKIP] Skipped live Notion check (add credentials to .env to enable).")
        test_results["notion_access"] = "Skipped (Dry Run)"

    # --------------------------------------------------------------------------
    # Step 5: Discord Approval Service Bridge (Member 2 Hand-off)
    # --------------------------------------------------------------------------
    print("\n[Step 5/5] Testing Discord Bot 'Approve' Callback Bridge...")
    try:
        bridge_res = publish_approved_doc(
            title="Staging Database Access Guide",
            markdown_content="To get credentials, email the DBA or access 1Password vault 'Dev-Staging'.",
            reviewer="charitardha#1234",
            source_question="Where do I get the staging database credentials?",
            tags=["staging", "database", "mysql"],
            use_skillpatch=True
        )
        print("  [PASS] Discord bridge handler function called successfully.")
        print(f"         Bridge Status: {bridge_res['status']}")
        test_results["discord_bridge"] = True
    except Exception as e:
        print(f"  [FAIL] Discord bridge execution failed: {e}")
        test_results["discord_bridge"] = False

    # --------------------------------------------------------------------------
    # Summary Report
    # --------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(" 📊 SILENT ONBOARDING PIPELINE STATUS REPORT")
    print("=" * 70)
    for k, v in test_results.items():
        status_label = "[PASS]" if v is True else ("[FAIL]" if v is False else f"[{v}]")
        print(f"  {status_label:<10} :: {k.upper()}")
    print("=" * 70)

    all_critical_passed = (
        test_results.get("skillpatch") is True and
        test_results.get("block_parser") is True and
        test_results.get("discord_bridge") is True
    )

    if all_critical_passed:
        print("\nAll integration code is verified and ready for Member 2 hand-off!")
    else:
        print("\nSome checks require attention.")

    return test_results


if __name__ == "__main__":
    run_pipeline_test()
