import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal, get_db
from models import Message, Draft, KeywordTracker, init_db
from ai import analyze_messages_and_generate_draft, search_knowledge_base, apply_draft_to_docs
from notion import sync_to_notion
import bot

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
AI_PROCESS_INTERVAL_MINUTES = int(os.getenv("AI_PROCESS_INTERVAL_MINUTES", "5"))

async def process_unprocessed_messages():
    """
    Background worker function that fetches unprocessed messages from SQLite,
    classifies & filters documentation-relevant topics, generates a targeted proposal,
    saves the draft, and sends to Discord approval channel.
    """
    while True:
        try:
            db = SessionLocal()
            try:
                unprocessed = db.query(Message).filter(Message.processed == 0).all()
                if unprocessed:
                    message_dicts = [
                        {"id": m.id, "user": m.user, "content": m.content, "channel_id": m.channel_id}
                        for m in unprocessed
                    ]
                    
                    # Generate AI draft with message filtering and FAQ classification
                    draft_data = analyze_messages_and_generate_draft(message_dicts)
                    
                    # Mark all batch messages as processed
                    for msg in unprocessed:
                        msg.processed = 1
                    db.commit()
                    
                    if draft_data:
                        # Save relevant draft into database
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
                        
                        print(f"[FastAPI Background Task] Created relevant doc draft #{new_draft.id} ({new_draft.priority} Priority) from {len(unprocessed)} messages.")
                        
                        # Send draft to Discord approval channel
                        if bot.bot.is_ready():
                            await bot.post_draft_for_approval(new_draft.id, new_draft.content, priority=new_draft.priority, target_section=new_draft.target_section, proposed_change=new_draft.proposed_change)
                    else:
                        print(f"[FastAPI Background Task] Processed {len(unprocessed)} messages (No documentation-relevant changes detected).")
            finally:
                db.close()
        except Exception as e:
            print(f"[FastAPI Background Task Error] {e}")

        # Sleep interval (e.g. 5 minutes or configured interval)
        await asyncio.sleep(AI_PROCESS_INTERVAL_MINUTES * 60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    init_db()
    
    # Start Discord Bot non-blocking if token is present
    bot_task = None
    if DISCORD_TOKEN and DISCORD_TOKEN != "your_discord_bot_token_here":
        bot_task = asyncio.create_task(bot.bot.start(DISCORD_TOKEN))
        print("[FastAPI Startup] Discord Bot task scheduled.")
    else:
        print("[FastAPI Startup Warning] DISCORD_TOKEN not configured or placeholder used.")

    # Start periodic background AI processing task
    ai_task = asyncio.create_task(process_unprocessed_messages())
    print("[FastAPI Startup] Background AI processor scheduled.")

    yield

    # Shutdown actions
    ai_task.cancel()
    if bot_task:
        await bot.bot.close()
        bot_task.cancel()

app = FastAPI(title="Discord AI Docs Backend", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "running", "service": "Discord AI Documentation Assistant"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/drafts")
def list_drafts(db: Session = Depends(get_db)):
    return db.query(Draft).all()

@app.get("/pending")
def list_pending_drafts(db: Session = Depends(get_db)):
    return db.query(Draft).filter(Draft.status == "Pending").order_by(Draft.id.desc()).all()

@app.get("/messages")
def list_messages(db: Session = Depends(get_db)):
    return db.query(Message).all()

@app.get("/keywords")
def list_keywords(db: Session = Depends(get_db)):
    return db.query(KeywordTracker).order_by(KeywordTracker.count.desc()).all()

@app.get("/search")
def search_docs(q: str):
    return {"query": q, "results": search_knowledge_base(q)}

@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    msg_total = db.query(Message).count()
    msg_unprocessed = db.query(Message).filter(Message.processed == 0).count()
    draft_total = db.query(Draft).count()
    draft_pending = db.query(Draft).filter(Draft.status == "Pending").count()
    draft_approved = db.query(Draft).filter(Draft.status == "Approved").count()
    draft_rejected = db.query(Draft).filter(Draft.status == "Rejected").count()
    top_kws = db.query(KeywordTracker).order_by(KeywordTracker.count.desc()).limit(5).all()
    
    return {
        "messages": {"total": msg_total, "unprocessed": msg_unprocessed},
        "drafts": {
            "total": draft_total,
            "pending": draft_pending,
            "approved": draft_approved,
            "rejected": draft_rejected
        },
        "top_keywords": [{"keyword": k.keyword, "count": k.count} for k in top_kws]
    }

@app.post("/trigger-ai-process")
async def trigger_ai_process(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Manual endpoint trigger to instantly run AI processing on pending messages.
    """
    unprocessed = db.query(Message).filter(Message.processed == 0).all()
    if not unprocessed:
        return {"status": "no unprocessed messages"}
    
    message_dicts = [
        {"id": m.id, "user": m.user, "content": m.content, "channel_id": m.channel_id}
        for m in unprocessed
    ]
    
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
        
        if bot.bot.is_ready():
            await bot.post_draft_for_approval(new_draft.id, new_draft.content, priority=new_draft.priority, target_section=new_draft.target_section, proposed_change=new_draft.proposed_change)
            
        return {"status": "success", "draft_created": True, "draft_id": new_draft.id, "priority": new_draft.priority}
    
    return {"status": "success", "draft_created": False, "reason": "No documentation-relevant topics detected"}

@app.post("/approve-all")
def approve_all_drafts(db: Session = Depends(get_db)):
    """
    Bulk-approves all pending drafts and updates documentation.
    """
    pending = db.query(Draft).filter(Draft.status == "Pending").all()
    if not pending:
        return {"status": "no pending drafts"}

    approved_ids = []
    for d in pending:
        d.status = "Approved"
        apply_draft_to_docs(
            draft_content=d.content,
            target_section=d.target_section,
            proposed_change=d.proposed_change,
            admin_notes=d.admin_notes
        )
        sync_to_notion(d.id, d.proposed_change or d.content)
        approved_ids.append(d.id)

    db.commit()
    return {"status": "success", "approved_count": len(approved_ids), "approved_ids": approved_ids}
