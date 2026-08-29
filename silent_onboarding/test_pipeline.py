import json
import os
import google.generativeai as genai
from ai_pipeline import detect_question, seed_docs, detect_gap, generate_draft

# 1. Configure API Key
# Replace "YOUR_API_KEY_HERE" with your actual Google AI Studio API Key!
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
genai.configure(api_key=API_KEY)

def run_test():
    print("--- Loading Mock Data ---")
    with open("mock_data.json", "r") as f:
        mock_data = json.load(f)
    
    print("1. Seeding Vector DB with existing docs...")
    seed_docs(mock_data["existing_docs"])
    print("Done!")

    import time
    print("\n2. Simulating Chat Messages...")
    for chat in mock_data["chat_logs"]:
        time.sleep(4) # Pause to avoid hitting free-tier rate limits!
        user = chat["user"]
        msg = chat["message"]
        print(f"\n[{user}]: {msg}")
        
        # Is it a question?
        is_q = detect_question(msg)
        if not is_q:
            print(" -> AI says: Not a question. Ignoring.")
            continue
            
        print(" -> AI says: This is a question! Checking docs...")
        
        # Is there a gap?
        gap_result = detect_gap(msg)
        print(f" -> Auditor Result: {gap_result}")
        
        if gap_result.get("has_gap"):
            print(" -> AI says: We have a documentation gap! Let's draft a new doc.")
            # Pretend a senior dev answered
            human_answer = "You just need to restart the server and clear the cache."
            draft = generate_draft(msg, [human_answer])
            print("\n--- DRAFT GENERATED ---")
            print(draft)
            print("-----------------------")
        else:
            print(" -> AI says: Already in docs. No action needed.")

if __name__ == "__main__":
    run_test()
