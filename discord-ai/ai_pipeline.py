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
    return response.choices[0].message.content.strip()

