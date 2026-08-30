import os
from typing import Any, Optional

import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from dotenv import load_dotenv

from database import SessionLocal
from models import Message, Draft, KeywordTracker, init_db
from notion import sync_to_notion
from ai import answer_onboarding_question, clean_markdown_formatting, apply_draft_to_docs, analyze_messages_and_generate_draft, extract_and_update_keywords, search_knowledge_base

load_dotenv()

ONBOARDING_CHANNEL_NAME = os.getenv("ONBOARDING_CHANNEL_NAME", "onboarding-help")
DOC_APPROVALS_CHANNEL_NAME = os.getenv("DOC_APPROVALS_CHANNEL_NAME", "doc-approvals")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def is_admin(user: Any) -> bool:
    """
    Checks if the user has administrator privileges in the server or carries an admin role.
    """
    if hasattr(user, "guild_permissions") and getattr(user.guild_permissions, "administrator", False):
        return True
    if hasattr(user, "roles"):
        for role in getattr(user, "roles", []):
            if role.name.lower() in ["admin", "administrator", "mod", "moderator"]:
                return True
    return False

class SuggestEditModal(Modal, title="Suggest Doc Correction / Edit"):
    def __init__(self, draft_id: int):
        super().__init__()
        self.draft_id = draft_id
        
        self.proposed_input = TextInput(
            label="Proposed Doc Update Content",
            style=discord.TextStyle.paragraph,
            placeholder="Enter or modify proposed documentation update...",
            required=True,
            max_length=2000
        )
        self.add_item(self.proposed_input)
        
        self.notes_input = TextInput(
            label="Admin Notes / Suggestions",
            style=discord.TextStyle.short,
            placeholder="Optional notes or feedback regarding this update...",
            required=False,
            max_length=500
        )
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("Permission Denied: Only administrators can submit suggestions or updates.", ephemeral=True)
            return

        db = SessionLocal()
        try:
            draft = db.query(Draft).filter(Draft.id == self.draft_id).first()
            if draft:
                draft.proposed_change = self.proposed_input.value
                draft.admin_notes = self.notes_input.value
                draft.status = "Approved"
                db.commit()

                # Update local documentation file directly
                apply_draft_to_docs(
                    draft_content=draft.content,
                    target_section=draft.target_section,
                    proposed_change=draft.proposed_change,
                    admin_notes=draft.admin_notes
                )

                # Sync to Notion
                sync_to_notion(draft.id, draft.proposed_change or draft.content)

                clean_summary = clean_markdown_formatting(
                    f"Draft #{draft.id} Approved with Admin Suggestions by {interaction.user.name}\n"
                    f"Priority: {draft.priority or 'Medium'}\n"
                    f"Target Section: {draft.target_section or 'General'}\n"
                    f"Updated Content:\n{draft.proposed_change}\n"
                    f"Admin Notes: {draft.admin_notes or 'None'}"
                )

                await interaction.response.send_message(
                    content=f"✅ {clean_summary}\nDocumentation updated successfully!",
                    ephemeral=False
                )
            else:
                await interaction.response.send_message("Draft not found in database.", ephemeral=True)
        finally:
            db.close()

class ApprovalView(View):
    def __init__(self, draft_id: int):
        super().__init__(timeout=None)
        self.draft_id = draft_id
        self.approve_button.custom_id = f"approve_btn:{draft_id}"
        self.suggest_button.custom_id = f"suggest_btn:{draft_id}"
        self.reject_button.custom_id = f"reject_btn:{draft_id}"

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("Permission Denied: Only administrators can approve documentation drafts.", ephemeral=True)
            return

        db = SessionLocal()
        try:
            draft = db.query(Draft).filter(Draft.id == self.draft_id).first()
            if draft:
                draft.status = "Approved"
                db.commit()
                
                # Apply update to local docs file
                apply_draft_to_docs(
                    draft_content=draft.content,
                    target_section=draft.target_section,
                    proposed_change=draft.proposed_change,
                    admin_notes=draft.admin_notes
                )
                
                # Sync to Notion
                sync_to_notion(draft.id, draft.proposed_change or draft.content)
                
                # Disable buttons
                for child in self.children:
                    child.disabled = True
                
                clean_msg = clean_markdown_formatting(interaction.message.content)
                await interaction.response.edit_message(
                    content=f"{clean_msg}\n\nStatus: ✅ Approved by Admin {interaction.user.name}",
                    view=self
                )
            else:
                await interaction.response.send_message("Draft not found in database.", ephemeral=True)
        finally:
            db.close()

    @discord.ui.button(label="Suggest / Edit", style=discord.ButtonStyle.blurple)
    async def suggest_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("Permission Denied: Only administrators can suggest edits or modify drafts.", ephemeral=True)
            return

        modal = SuggestEditModal(draft_id=self.draft_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("Permission Denied: Only administrators can reject documentation drafts.", ephemeral=True)
            return

        db = SessionLocal()
        try:
            draft = db.query(Draft).filter(Draft.id == self.draft_id).first()
            if draft:
                draft.status = "Rejected"
                db.commit()
                
                for child in self.children:
                    child.disabled = True
                
                clean_msg = clean_markdown_formatting(interaction.message.content)
                await interaction.response.edit_message(
                    content=f"{clean_msg}\n\nStatus: ❌ Rejected by Admin {interaction.user.name}",
                    view=self
                )
            else:
                await interaction.response.send_message("Draft not found in database.", ephemeral=True)
        finally:
            db.close()

@bot.event
async def on_ready():
    # Register persistent views for all pending drafts in database on startup
    db = SessionLocal()
    try:
        pending_drafts = db.query(Draft).filter(Draft.status == "Pending").all()
        for draft in pending_drafts:
            bot.add_view(ApprovalView(draft_id=draft.id))
        print(f"[Bot] Registered {len(pending_drafts)} persistent approval views.")
    except Exception as e:
        print(f"[Bot Startup Error] Persistent view registration failed: {e}")
    finally:
        db.close()
    
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    channel_name = getattr(message.channel, 'name', '')

    # Check if message is in #onboarding-help channel
    if channel_name == ONBOARDING_CHANNEL_NAME:
        # Block command usage inside #onboarding-help channel
        if message.content.startswith(bot.command_prefix):
            await message.reply("⚠️ Bot commands are disabled in `#onboarding-help`")
            return

        db = SessionLocal()
        extracted_kw = {}
        try:
            msg_record = Message(
                id=str(message.id),
                user=str(message.author),
                content=message.content,
                timestamp=message.created_at,
                channel_id=str(message.channel.id)
            )
            db.add(msg_record)
            db.commit()
            
            # Persistently track & increment keyword frequencies
            extracted_kw = extract_and_update_keywords(message.content, db)
            
            print(f"[Listener] Logged message {message.id} from {message.author} and updated keywords: {list(extracted_kw.keys())}")
        except Exception as e:
            print(f"[Listener Error] Failed to log message: {e}")
            db.rollback()
        finally:
            db.close()

        # Always reply if keywords are present or user is asking an onboarding/setup question
        if extracted_kw or "?" in message.content or bot.user in message.mentions or any(k in message.content.lower() for k in ["how", "help", "setup", "where", "python", "env", "error", "fastapi", "db", "pip", "discord", "token", "run", "issue", "bot"]):
            ai_reply = answer_onboarding_question(message.content)
            await message.reply(ai_reply)

        # Strictly prevent command processing in #onboarding-help
        return

    await bot.process_commands(message)

async def post_draft_for_approval(draft_id: int, content: str, priority: str = "Medium", target_section: Optional[str] = None, proposed_change: Optional[str] = None, target_channel: Optional[Any] = None):
    """
    Posts draft content with clean formatting and Approve/Suggest/Reject UI buttons strictly to #doc-approvals.
    """
    clean_content = clean_markdown_formatting(content)
    view = ApprovalView(draft_id=draft_id)
    msg_text = (
        f"📝 Documentation Update Draft #{draft_id}\n"
        f"Priority: {priority}\n"
        f"Target Section: {target_section or 'General Troubleshooting'}\n\n"
        f"{clean_content}"
    )

    if target_channel:
        await target_channel.send(content=msg_text, view=view)
        print(f"[Approver] Posted draft #{draft_id} to provided channel {target_channel.name}")
        return True

    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=DOC_APPROVALS_CHANNEL_NAME)
        if channel:
            await channel.send(content=msg_text, view=view)
            print(f"[Approver] Posted draft #{draft_id} (Priority: {priority}) to #{channel.name}")
            return True

    print(f"[Approver Error] Target approval channel #{DOC_APPROVALS_CHANNEL_NAME} not found.")
    return False

@bot.command(name="testdoc")
async def test_doc_command(ctx):
    """
    Command to manually trigger the doc approval UI for testing. Usage: !testdoc
    """
    if not is_admin(ctx.author):
        await ctx.send("Permission Denied: Only administrators can trigger test documentation drafts.")
        return

    test_content = "This is a test documentation draft update for python environment activation."
    db = SessionLocal()
    try:
        new_draft = Draft(
            content=test_content,
            priority="Medium",
            target_section="Environment Setup",
            proposed_change=test_content,
            status="Pending"
        )
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        
        success = await post_draft_for_approval(
            draft_id=new_draft.id,
            content=new_draft.content,
            priority=new_draft.priority,
            target_section=new_draft.target_section,
            proposed_change=new_draft.proposed_change
        )
        if success:
            await ctx.send(f"Test draft #{new_draft.id} posted to the approval channel.")
        else:
            await ctx.send("Failed to post draft. Check your terminal logs.")
    finally:
        db.close()

@bot.command(name="status")
async def status_command(ctx):
    """
    Shows system statistics: message count and draft count. Usage: !status
    """
    db = SessionLocal()
    try:
        msg_count = db.query(Message).count()
        unprocessed_count = db.query(Message).filter(Message.processed == 0).count()
        draft_count = db.query(Draft).count()
        pending_drafts = db.query(Draft).filter(Draft.status == "Pending").count()
        
        status_text = (
            f"📊 System Status\n"
            f"Logged Messages - Total: {msg_count} | Unprocessed: {unprocessed_count}\n"
            f"Documentation Drafts - Total: {draft_count} | Pending Approval: {pending_drafts}"
        )
        await ctx.send(status_text)
    finally:
        db.close()

@bot.command(name="drafts")
async def drafts_command(ctx):
    """
    Lists recent documentation proposals sorted by ID, displaying priority, section, and status cleanly. Usage: !drafts
    """
    db = SessionLocal()
    try:
        drafts = db.query(Draft).order_by(Draft.id.desc()).limit(5).all()
        if not drafts:
            await ctx.send("No documentation drafts found.")
            return
            
        lines = ["📝 Recent Documentation Change Proposals:\n"]
        for d in drafts:
            status_emoji = "✅" if d.status == "Approved" else ("❌" if d.status == "Rejected" else "⏳")
            clean_content = clean_markdown_formatting(d.content[:200])
            lines.append(
                f"{status_emoji} Draft #{d.id} | Priority: {d.priority or 'Medium'} | Status: {d.status} | Target: {d.target_section or 'General'}\n"
                f"Preview: {clean_content}...\n"
            )
            
        await ctx.send("\n".join(lines))
    finally:
        db.close()

@bot.command(name="approve")
async def approve_command(ctx, draft_id: int):
    """
    Manually approves a draft proposal by ID. Usage: !approve <draft_id> (Admin only)
    """
    if not is_admin(ctx.author):
        await ctx.send("Permission Denied: Only administrators can approve documentation drafts.")
        return

    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft:
            await ctx.send(f"Draft #{draft_id} not found.")
            return
        
        draft.status = "Approved"
        db.commit()

        # Update local docs file
        apply_draft_to_docs(
            draft_content=draft.content,
            target_section=draft.target_section,
            proposed_change=draft.proposed_change,
            admin_notes=draft.admin_notes
        )

        sync_to_notion(draft.id, draft.proposed_change or draft.content)
        await ctx.send(f"✅ Draft #{draft_id} approved by Admin {ctx.author.name} and documentation updated!")
    finally:
        db.close()

@bot.command(name="reject")
async def reject_command(ctx, draft_id: int):
    """
    Manually rejects a draft proposal by ID. Usage: !reject <draft_id> (Admin only)
    """
    if not is_admin(ctx.author):
        await ctx.send("Permission Denied: Only administrators can reject documentation drafts.")
        return

    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft:
            await ctx.send(f"Draft #{draft_id} not found.")
            return
        
        draft.status = "Rejected"
        db.commit()
        await ctx.send(f"❌ Draft #{draft_id} marked as Rejected by Admin {ctx.author.name}.")
    finally:
        db.close()

@bot.command(name="trigger_ai")
async def trigger_ai_command(ctx):
    """
    Manually triggers AI processing for unprocessed onboarding messages. Usage: !trigger_ai
    """
    await ctx.send("🔄 Triggering AI message processing and FAQ analysis...")
    db = SessionLocal()
    try:
        unprocessed = db.query(Message).filter(Message.processed == 0).all()
        if not unprocessed:
            await ctx.send("No new unprocessed messages found in onboarding-help.")
            return
            
        message_dicts = [{"id": m.id, "user": m.user, "content": m.content, "channel_id": m.channel_id} for m in unprocessed]
        
        draft_data = analyze_messages_and_generate_draft(message_dicts)
        
        for msg in unprocessed:
            msg.processed = 1
        db.commit()
        
        if draft_data:
            new_draft = Draft(
                content=draft_data["content"],
                priority=draft_data.get("priority", "Medium"),
                target_section=draft_data.get("target_section", "General"),
                proposed_change=draft_data.get("proposed_change", draft_data["content"]),
                status="Pending"
            )
            db.add(new_draft)
            db.commit()
            db.refresh(new_draft)
            
            await post_draft_for_approval(
                draft_id=new_draft.id,
                content=new_draft.content,
                priority=new_draft.priority,
                target_section=new_draft.target_section,
                proposed_change=new_draft.proposed_change
            )
            await ctx.send(f"✅ Created Draft #{new_draft.id} ({new_draft.priority} Priority) and posted to {DOC_APPROVALS_CHANNEL_NAME}!")
        else:
            await ctx.send("Analyzed messages: No documentation-relevant issues detected.")
    finally:
        db.close()

@bot.command(name="keywords")
async def keywords_command(ctx):
    """
    Shows top tracked onboarding keywords and their persistent frequency counts. Usage: !keywords
    """
    db = SessionLocal()
    try:
        keywords = db.query(KeywordTracker).order_by(KeywordTracker.count.desc()).limit(10).all()
        if not keywords:
            await ctx.send("No keywords tracked yet.")
            return

        lines = ["🔑 Top Tracked Onboarding Keywords & Counts:\n"]
        for k in keywords:
            lines.append(f"• {k.keyword}: {k.count} occurrences")

        await ctx.send("\n".join(lines))
    finally:
        db.close()

@bot.command(name="pending")
async def pending_command(ctx):
    """
    Lists all documentation drafts currently pending admin approval. Usage: !pending
    """
    db = SessionLocal()
    try:
        pending_drafts = db.query(Draft).filter(Draft.status == "Pending").order_by(Draft.id.desc()).all()
        if not pending_drafts:
            await ctx.send("⏳ No pending documentation drafts at this time.")
            return

        lines = [f"⏳ Pending Documentation Drafts ({len(pending_drafts)} total):\n"]
        for d in pending_drafts:
            clean_preview = clean_markdown_formatting(d.content[:150])
            lines.append(
                f"• Draft #{d.id} | Priority: {d.priority or 'Medium'} | Target: {d.target_section or 'General'}\n"
                f"  Preview: {clean_preview}...\n"
            )

        await ctx.send("\n".join(lines))
    finally:
        db.close()

@bot.command(name="approve_all")
async def approve_all_command(ctx):
    """
    Approves all pending documentation drafts at once and updates documentation. Usage: !approve_all (Admin only)
    """
    if not is_admin(ctx.author):
        await ctx.send("Permission Denied: Only administrators can approve documentation drafts.")
        return

    db = SessionLocal()
    try:
        pending_drafts = db.query(Draft).filter(Draft.status == "Pending").all()
        if not pending_drafts:
            await ctx.send("No pending documentation drafts to approve.")
            return

        approved_count = 0
        for draft in pending_drafts:
            draft.status = "Approved"
            apply_draft_to_docs(
                draft_content=draft.content,
                target_section=draft.target_section,
                proposed_change=draft.proposed_change,
                admin_notes=draft.admin_notes
            )
            sync_to_notion(draft.id, draft.proposed_change or draft.content)
            approved_count += 1

        db.commit()
        await ctx.send(f"✅ Approved {approved_count} pending draft(s) at once and updated documentation!")
    finally:
        db.close()

@bot.command(name="bothelp", aliases=["help_docs", "commands"])
async def bothelp_command(ctx):
    """
    Displays complete help guide and available bot commands. Usage: !bothelp
    """
    admin_flag = " (Administrator)" if is_admin(ctx.author) else ""
    help_text = (
        f"🤖 Onboarding AI Assistant & Documentation Manager Guide{admin_flag}\n\n"
        f"📖 Member Commands (Run in #doc-approvals or general channels):\n"
        f"• Ask Questions: Type any onboarding or setup question in #onboarding-help to get instant AI answers!\n"
        f"• !search_docs <query> : Search the knowledge base for specific topics.\n"
        f"• !keywords : View top tracked onboarding keywords & frequency counts.\n"
        f"• !status : View total logged messages and draft counts.\n"
        f"• !metrics : View comprehensive analytics & status breakdown.\n"
        f"• !bothelp : Show this help menu.\n\n"
        f"🛠️ Admin Commands (Restricted to Server Administrators in management channels):\n"
        f"• !pending : View all documentation proposals awaiting review.\n"
        f"• !drafts : View recent documentation update proposals.\n"
        f"• !approve <draft_id> : Approve a single draft and auto-update onboarding documentation.\n"
        f"• !approve_all : Bulk-approve ALL pending documentation drafts at once.\n"
        f"• !reject <draft_id> : Reject a draft proposal.\n"
        f"• !trigger_ai : Force-trigger AI processing for unprocessed user messages.\n"
        f"• !testdoc : Generate a test draft with interactive Approve/Suggest/Reject UI buttons.\n\n"
        f"Note: Bot commands are disabled in #onboarding-help to keep chat clean."
    )
    await ctx.send(help_text)

@bot.command(name="search_docs", aliases=["search"])
async def search_docs_command(ctx, *, query: str):
    """
    Searches the onboarding knowledge base for matching keywords or text. Usage: !search_docs <query>
    """
    result = search_knowledge_base(query)
    await ctx.send(result)

@bot.command(name="metrics")
async def metrics_command(ctx):
    """
    Shows comprehensive project metrics: message counts, draft breakdown, and top keywords. Usage: !metrics
    """
    db = SessionLocal()
    try:
        msg_total = db.query(Message).count()
        msg_unprocessed = db.query(Message).filter(Message.processed == 0).count()
        
        draft_total = db.query(Draft).count()
        draft_pending = db.query(Draft).filter(Draft.status == "Pending").count()
        draft_approved = db.query(Draft).filter(Draft.status == "Approved").count()
        draft_rejected = db.query(Draft).filter(Draft.status == "Rejected").count()
        
        top_kws = db.query(KeywordTracker).order_by(KeywordTracker.count.desc()).limit(5).all()
        kw_text = ", ".join([f"{k.keyword} ({k.count})" for k in top_kws]) if top_kws else "None"

        metrics_text = (
            f"📈 System Metrics & Analytics\n"
            f"Messages Logged: Total: {msg_total} | Unprocessed: {msg_unprocessed}\n"
            f"Drafts Breakdown: Total: {draft_total} | Pending: {draft_pending} | Approved: {draft_approved} | Rejected: {draft_rejected}\n"
            f"Top Keywords: {kw_text}"
        )
        await ctx.send(metrics_text)
    finally:
        db.close()

#bot.run(os.getenv("DISCORD_TOKEN"))

