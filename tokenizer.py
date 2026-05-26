import os
import sys
import cohere
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    # Path to knowledge-base
    kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge-base")
    if not os.path.exists(kb_path):
        print(f"Error: {kb_path} not found.")
        sys.exit(1)
        
    with open(kb_path, "r", encoding="utf-8") as f:
        kb_text = f.read()

    # Get Cohere API Key
    api_key = os.getenv("COHERE_API")
    if not api_key:
        print("Error: COHERE_API environment variable not set. Please set it in .env or your environment.")
        sys.exit(1)

    try:
        # Initialize Cohere ClientV2
        co = cohere.ClientV2(api_key=api_key)
        
        # Tokenize using the model
        print("Tokenizing knowledge-base using model command-a-03-2025...")
        # Note: offline=False uses the hosted API rather than local cache if downloading config fails
        response = co.tokenize(text=kb_text, model="command-a-03-2025", offline=False)
        
        token_count = len(response.tokens)
        print(f"Success! Token count: {token_count}")
        
    except Exception as e:
        print(f"Error calling Cohere API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
