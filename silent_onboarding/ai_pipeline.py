import google.generativeai as genai
import chromadb
import uuid
import json

# Initialize ChromaDB persistent client and the target collection
chroma_client = chromadb.PersistentClient(path="./chroma_db")
wiki_collection = chroma_client.get_or_create_collection(name="wiki_docs")

def detect_question(message: str) -> bool:
 """
 Uses a Gemini LLM prompt to return True ONLY if the message is a 
 genuine technical/onboarding question.
 """
 model = genai.GenerativeModel('gemini-3.5-flash')
 
 prompt = (
 "You are an AI assistant monitoring a developer chat. "
 "Analyze the following message and determine if it is a genuine "
 "technical or onboarding question (e.g., asking for help, documentation, "
 "or how to do a task). Ignore casual greetings or off-topic chatter.\n\n"
 "Return ONLY the word 'True' if it is a technical/onboarding question, "
 "or 'False' if it is not.\n\n"
 f"Message: \"{message}\""
 )
 
 response = model.generate_content(prompt)
 
 # Strip whitespace and normalize to lowercase to safely evaluate the boolean
 result = response.text.strip().lower()
 return result == 'true'

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
 
 model = genai.GenerativeModel("gemini-3.5-flash")
 
 # Using response_mime_type to guarantee valid JSON output
 response = model.generate_content(
  prompt,
  generation_config=genai.GenerationConfig(response_mime_type="application/json")
 )
 
 try:
  return json.loads(response.text)
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
 
 model = genai.GenerativeModel("gemini-1.5-flash")
 response = model.generate_content(prompt)
 
 return response.text
