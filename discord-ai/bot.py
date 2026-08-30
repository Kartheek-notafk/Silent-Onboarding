import os
from typing import Any, cast

import discord
from discord.ext import commands
from discord.ui import Button, View
from datetime import datetime
from dotenv import load_dotenv

import asyncio
from database import SessionLocal
from models import Message, Draft, init_db
from notion import sync_to_notion
from ai_pipeline import detect_question, detect_gap

load_dotenv()

ONBOARDING_CHANNEL_NAME = os.getenv("ONBOARDING_CHANNEL_NAME", "onboarding-help")
DOC_APPROVALS_CHANNEL_NAME = os.getenv("DOC_APPROVALS_CHANNEL_NAME", "doc-approvals")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class ApprovalView(View):
    def __init__(self, draft_id: int):
        super().__init__(timeout=None)
        self.draft_id = draft_id
        # Dynamic custom_id encoding the draft_id for persistent state across restarts
        self.approve_button.custom_id = f"approve_btn:{draft_id}"
        self.reject_button.custom_id = f"reject_btn:{draft_id}"

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: discord.Interaction, button: Button):
        db = SessionLocal()
        try:
            draft = db.query(Draft).filter(Draft.id == self.draft_id).first()
            if draft:
                draft.status = "Approved"
                db.commit()
                
                # Trigger Notion integration script
                sync_to_notion(draft.id, draft.content)
                
                # Disable buttons and update message UI
                for child in self.children:
                    child.disabled = True
                
                await interaction.response.edit_message(
                    content=f"{interaction.message.content}\n\n**Status:** ✅ Approved by {interaction.user.name}",
                    view=self
                )
            else:
                await interaction.response.send_message("Draft not found in database.", ephemeral=True)
        finally:
            db.close()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: Button):
        db = SessionLocal()
        try:
            draft = db.query(Draft).filter(Draft.id == self.draft_id).first()
            if draft:
                draft.status = "Rejected"
                db.commit()
                
                # Disable buttons and update message UI
                for child in self.children:
                    child.disabled = True
                
                await interaction.response.edit_message(
                    content=f"{interaction.message.content}\n\n**Status:** ❌ Rejected by {interaction.user.name}",
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

    # Process commands first
    await bot.process_commands(message)
    if message.content.startswith('!'):
        return

    # Check if message is in #onboarding-help channel
    if getattr(message.channel, 'name', '') == ONBOARDING_CHANNEL_NAME:
        db = SessionLocal()
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
            print(f"[Listener] Logged message {message.id} from {message.author}")
        except Exception as e:
            print(f"[Listener Error] Failed to log message: {e}")
            db.rollback()
        finally:
            db.close()

        # Use AI Pipeline to determine if this is a genuine question
        try:
            is_question = await asyncio.to_thread(detect_question, message.content)
            if is_question:
                audit = await asyncio.to_thread(detect_gap, message.content)
                if not audit.get("has_gap"):
                    # Already in docs! Reply instantly.
                    await message.channel.send(f"🤖 **Documentation Assistant:**\n{audit.get('reason')}")
        except Exception as e:
            print(f"[AI Pipeline Error] {e}")

async def post_draft_for_approval(draft_id: int, content: str):
    """
    Posts draft content to #doc-approvals with Approve and Reject UI buttons.
    """
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=DOC_APPROVALS_CHANNEL_NAME)
        if channel:
            view = ApprovalView(draft_id=draft_id)
            safe_content = content[:1900] + ("..." if len(content) > 1900 else "")
            msg_text = f"📝 **New AI Documentation Draft #{draft_id}**\n\n{safe_content}"
            await channel.send(content=msg_text, view=view)
            print(f"[Approver] Posted draft #{draft_id} to #{DOC_APPROVALS_CHANNEL_NAME}")
            return True
    print(f"[Approver Error] Target channel #{DOC_APPROVALS_CHANNEL_NAME} not found in available guilds.")
    return False

@bot.command(name="testdoc")
async def test_doc_command(ctx):
    """
    Temporary command to manually trigger the doc approval UI. Usage: !testdoc
    """
    test_content = "This is a test documentation draft. If you see this, this should be working."
    db = SessionLocal()
    try:
        new_draft = Draft(content=test_content, status="Pending")
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        
        success = await post_draft_for_approval(draft_id=new_draft.id, content=new_draft.content)
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
        
        embed = discord.Embed(title="📊 System Status", color=discord.Color.blue())
        embed.add_field(name="Logged Messages", value=f"Total: {msg_count}\nUnprocessed: {unprocessed_count}", inline=True)
        embed.add_field(name="Documentation Drafts", value=f"Total: {draft_count}\nPending Approval: {pending_drafts}", inline=True)
        await ctx.send(embed=embed)
    finally:
        db.close()

@bot.command(name="drafts")
async def drafts_command(ctx):
    """
    Lists recent documentation proposals, extracting frequently asked questions and proposed doc changes. Usage: !drafts
    """
    db = SessionLocal()
    try:
        drafts = db.query(Draft).order_by(Draft.id.desc()).limit(5).all()
        if not drafts:
            await ctx.send("No documentation drafts found.")
            return
            
        embed = discord.Embed(
            title="📝 Repeated Questions & Documentation Change Proposals",
            description="Recent AI-analyzed onboarding topics and proposed documentation updates:",
            color=discord.Color.gold()
        )
        
        for d in drafts:
            content = d.content
            # Extract key sections (FAQ/Questions and Suggested Changes) for clean display
            status_emoji = "✅" if d.status == "Approved" else ("❌" if d.status == "Rejected" else "⏳")
            
            # Format preview snippet focusing on questions/suggestions
            lines = content.split("\n")
            preview_lines = [l for l in lines if l.strip().startswith("-") or l.strip().startswith("1.") or l.strip().startswith("2.") or "Question" in l or "Category" in l]
            
            if preview_lines:
                preview_text = "\n".join(preview_lines[:5])
            else:
                preview_text = content[:250] + ("..." if len(content) > 250 else "")
                
            embed.add_field(
                name=f"{status_emoji} Draft #{d.id} | Status: {d.status}",
                value=f"```markdown\n{preview_text}\n```",
                inline=False
            )
            
        await ctx.send(embed=embed)
    finally:
        db.close()

@bot.command(name="approve")
async def approve_command(ctx, draft_id: int):
    """
    Manually approves a draft proposal by ID. Usage: !approve <draft_id>
    """
    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft:
            await ctx.send(f"❌ Draft #{draft_id} not found.")
            return
        
        draft.status = "Approved"
        db.commit()
        sync_to_notion(draft.id, draft.content)
        await ctx.send(f"✅ Draft #{draft_id} marked as **Approved** and synced to Notion!")
    finally:
        db.close()

@bot.command(name="reject")
async def reject_command(ctx, draft_id: int):
    """
    Manually rejects a draft proposal by ID. Usage: !reject <draft_id>
    """
    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft:
            await ctx.send(f"❌ Draft #{draft_id} not found.")
            return
        
        draft.status = "Rejected"
        db.commit()
        await ctx.send(f"❌ Draft #{draft_id} marked as **Rejected**.")
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
            await ctx.send("ℹ️ No new unprocessed messages found in `#onboarding-help`.")
            return
            
        from ai_pipeline import process_message_batch
        message_dicts = [{"id": m.id, "user": m.user, "content": m.content, "channel_id": m.channel_id} for m in unprocessed]
        
        draft_content = process_message_batch(message_dicts)
        
        for msg in unprocessed:
            msg.processed = 1
        db.commit()
        
        if draft_content:
            new_draft = Draft(content=draft_content, status="Pending")
            db.add(new_draft)
            db.commit()
            db.refresh(new_draft)
            
            await post_draft_for_approval(new_draft.id, new_draft.content)
            await ctx.send(f"✅ Created Draft #{new_draft.id} and posted to `{DOC_APPROVALS_CHANNEL_NAME}`!")
        else:
            await ctx.send("ℹ️ Analyzed messages: No documentation-relevant issues detected.")
    finally:
        db.close()

#bot.run(os.getenv("DISCORD_TOKEN"))

