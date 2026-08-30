import os
import google.generativeai as genai
import chromadb
import uuid
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Initialize ChromaDB persistent client and the target collection
chroma_client = chromadb.PersistentClient(path="./chroma_db")
wiki_collection = chroma_client.get_or_create_collection(name="wiki_docs")

def detect_question(message: str) -> bool:
 """
 Uses a Groq LLM prompt to return True ONLY if the message is a 
 genuine technical/onboarding question.
 """
 
 prompt = (
 "You are an AI assistant monitoring a developer chat. "
 "Analyze the following message and determine if it is a genuine "
 "technical or onboarding question (e.g., asking for help, documentation, "
 "or how to do a task). Ignore casual greetings or off-topic chatter.\n\n"
 "Return ONLY the word 'True' if it is a technical/onboarding question, "
 "or 'False' if it is not.\n\n"
 f"Message: \"{message}\""
 )
 
 response = groq_client.chat.completions.create(
     model="groq/compound-mini",
     messages=[{"role": "user", "content": prompt}],
     temperature=0
 )
 
 # Strip whitespace and normalize to lowercase to safely evaluate the boolean
 result = response.choices[0].message.content.strip().lower()
 return 'true' in result

def get_embedding(text: str) -> list[float]:
 """
 Uses Gemini's gemini-embedding-2 model to return a semantic vector array 
 for a given text.
 """
 response = genai.embed_content(
 model="models/gemini-embedding-2",
 content=text,
 task_type="retrieval_document"
 )
 
 return response['embedding']

def seed_docs(docs: list[str]):
 """
 Takes an array of strings, gets their vectors, and stores them in ChromaDB.
 Assumes `get_embedding()` is already defined in the file.
 """
 if not docs:
  return
 
 embeddings = [get_embedding(doc) for doc in docs]
 ids = [str(uuid.uuid4()) for _ in docs]
 
 wiki_collection.upsert(
  documents=docs,
  embeddings=embeddings,
  ids=ids
 )

def detect_gap(question: str) -> dict:
 """
 Finds nearest neighbors for a question and audits the docs using Gemini.
 Assumes `get_embedding()` is already defined in the file.
 """
 question_embedding = get_embedding(question)
 
 # Query for the top 2 nearest neighbors
 results = wiki_collection.query(
  query_embeddings=[question_embedding],
  n_results=2
 )
 
 retrieved_docs = results["documents"][0] if results["documents"] else []
 docs_context = "\n\n---\n\n".join(retrieved_docs)
 
 prompt = f"""You are a Documentation Auditor. 
 Read the Question and the retrieved Documentation Context below. 
 Determine if the documentation provides a complete answer to the question.
 
 Return your response strictly as JSON with this schema:
 {{"has_gap": true/false, "reason": "your reasoning here"}}

 Question: {question}
 
 Documentation Context:
 {docs_context}
 """
 
 response = groq_client.chat.completions.create(
     model="groq/compound-mini",
     messages=[{"role": "user", "content": prompt}],
     response_format={"type": "json_object"},
     temperature=0
 )
 
 try:
  return json.loads(response.choices[0].message.content)
 except json.JSONDecodeError:
  return {"has_gap": True, "reason": "Failed to parse auditor response"}

def generate_draft(question: str, human_answers: list[str]) -> str:
 """
 Takes a question and human answers, returning a Markdown-formatted Wiki section.
 """
 formatted_answers = "\n".join(f"- {answer}" for answer in human_answers)
 
 prompt = f"""You are a Technical Writer.
 Your task is to write a clean, well-structured Markdown section that will be appended directly to a Wiki page.
 Use the question and the provided human answers to synthesize a comprehensive, professional entry.
 
 Question: {question}
 
 Source Material (Human Answers):
 {formatted_answers}
 """
 
 response = groq_client.chat.completions.create(
     model="groq/compound-mini",
     messages=[{"role": "user", "content": prompt}]
 )
 
 return response.choices[0].message.content


def process_message_batch(messages: list[dict]) -> str | None:
    """
    Takes a batch of messages, finds unresolved questions, and generates a combined documentation draft.
    Returns None if no gaps are found.
    """
    gaps_found = []
    
    for msg in messages:
        content = msg.get("content", "")
        if detect_question(content):
            audit = detect_gap(content)
            if audit.get("has_gap"):
                gaps_found.append(content)
                
    if not gaps_found:
        return None
        
    # Generate a draft for the gaps using the human answers context if needed
    # For now, we ask the AI to draft a doc covering these missing questions
    prompt = "The following questions were asked by new hires, but are missing from our documentation:\n"
    for q in gaps_found:
        prompt += f"- {q}\n"
    prompt += "\nPlease write a professional Markdown documentation update that addresses these topics."
    
    response = groq_client.chat.completions.create(
        model="groq/compound-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    content = response.choices[0].message.content.strip()
    return {
        "content": content,
        "priority": "Medium",
        "target_section": "Common Onboarding Issues & Troubleshooting",
        "proposed_change": content
    }

import re
from datetime import datetime
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

def extract_and_update_keywords(content: str, db_session) -> dict:
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

def clean_markdown_formatting(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'^[ \t]*#+[ \t]*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'```[a-zA-Z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    return text.strip()

def apply_draft_to_docs(draft_content: str, target_section: str = None, proposed_change: str = None, admin_notes: str = None) -> bool:
    kb_path = os.path.join(os.path.dirname(__file__), "docs", "onboarding_knowledge_base.md")
    try:
        content_to_add = proposed_change if proposed_change else draft_content
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        section_title = target_section if target_section else "General Troubleshooting & Updates"
        entry = f"\n\n### Section: {section_title} (Admin Approved: {timestamp})\n"
        entry += f"{clean_markdown_formatting(content_to_add)}\n"
        if admin_notes:
            entry += f"Admin Note/Correction: {clean_markdown_formatting(admin_notes)}\n"
        
        # Make sure directory exists
        os.makedirs(os.path.dirname(kb_path), exist_ok=True)
        with open(kb_path, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"[Docs Update] Applied approved draft changes to {kb_path}")
        return True
    except Exception as e:
        print(f"[Docs Update Error] Failed to update docs file: {e}")
        return False

def search_knowledge_base(query: str) -> str:
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
            return f"No direct documentation matches found for '{query}'." 
    except Exception as e:
        return f"Error searching knowledge base: {e}"

def answer_onboarding_question(question: str) -> str:
    try:
        kb_path = os.path.join(os.path.dirname(__file__), "docs", "onboarding_knowledge_base.md")
        kb_context = ""
        if os.path.exists(kb_path):
            with open(kb_path, "r", encoding="utf-8") as f:
                kb_context = f.read()
        prompt = f"You are an intelligent Onboarding AI Assistant.\nProject Knowledge Base:\n{kb_context}\n\nUser Question:\n\"{question}\"\nProvide a extremely concise, helpful, and direct summary of the solution. You MUST keep your response strictly under 1500 characters. Do NOT use ugly markdown syntax like **, ##, ###."
        response = groq_client.chat.completions.create(model="groq/compound-mini", messages=[{"role": "user", "content": prompt}])
        return clean_markdown_formatting(response.choices[0].message.content.strip())
    except Exception as e:
        return f"Onboarding AI Assistant:\nRegarding your question: \"{question}\"\nPlease check docs/onboarding_knowledge_base.md for full details."

