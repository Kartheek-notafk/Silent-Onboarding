import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal, get_db
from models import Message, Draft, init_db
from ai_pipeline import process_message_batch
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
    await bot.bot.wait_until_ready()
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
                    
                    # Generate AI draft using the ChromaDB RAG Pipeline in a background thread
                    draft_content = await asyncio.to_thread(process_message_batch, message_dicts)
                    
                    # Mark all batch messages as processed
                    for msg in unprocessed:
                        msg.processed = 1
                    db.commit()
                    
                    if draft_content:
                        # Save relevant draft into database
                        new_draft = Draft(
                            content=draft_content["content"],
                            priority=draft_content.get("priority", "Medium"),
                            target_section=draft_content.get("target_section", "General"),
                            proposed_change=draft_content.get("proposed_change", draft_content["content"]),
                            status="Pending"
                        )
                        db.add(new_draft)
                        db.commit()
                        db.refresh(new_draft)
                        
                        print(f"[FastAPI Background Task] Created relevant doc draft #{new_draft.id} from {len(unprocessed)} messages.")
                        
                        # Send draft to Discord approval channel
                        if bot.bot.is_ready():
                            await bot.post_draft_for_approval(
                                draft_id=new_draft.id,
                                content=new_draft.content,
                                priority=new_draft.priority,
                                target_section=new_draft.target_section,
                                proposed_change=new_draft.proposed_change
                            )
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

@app.get("/messages")
def list_messages(db: Session = Depends(get_db)):
    return db.query(Message).all()

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
    
    draft_content = await asyncio.to_thread(process_message_batch, message_dicts)
    
    for msg in unprocessed:
        msg.processed = 1
    db.commit()
    
    if draft_content:
        new_draft = Draft(
            content=draft_content["content"],
            priority=draft_content.get("priority", "Medium"),
            target_section=draft_content.get("target_section", "General"),
            proposed_change=draft_content.get("proposed_change", draft_content["content"]),
            status="Pending"
        )
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        
        if bot.bot.is_ready():
            await bot.post_draft_for_approval(
                draft_id=new_draft.id,
                content=new_draft.content,
                priority=new_draft.priority,
                target_section=new_draft.target_section,
                proposed_change=new_draft.proposed_change
            )
            
        return {"status": "success", "draft_created": True, "draft_id": new_draft.id}
    
    return {"status": "success", "draft_created": False, "reason": "No documentation-relevant topics detected"}

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "dashboard.html")
    try:
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Dashboard file not found. Ensure dashboard.html is in the parent directory.</h1>"

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_questions = db.query(Message).count()
    docs_updated = db.query(Draft).filter(Draft.status == "Approved").count()
    hours_saved = docs_updated * 2
    return {
        "total_questions": total_questions,
        "docs_updated": docs_updated,
        "hours_saved": hours_saved
    }
