import os
import sys
import httpx
from dotenv import load_dotenv
from langchain_groq import ChatGroq
load_dotenv()
def create_llm():
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    http_client = httpx.Client(verify=False)
    return ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.1,
        groq_api_key=api_key,
        http_client=http_client
    )

def main():
    if len(sys.argv) < 2:
        print("Usage: python groq_prompt.py \"Your prompt here\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Sending prompt: {prompt}")
    llm = create_llm()  # Create the ChatGroq client
    try:
        # Adjust the call according to the ChatGroq API.
        response = llm.invoke(prompt)  # Send the prompt to Groq
        print("Response from Groq:")
        print(response)
    except Exception as e:
        print(f"Error communicating with Groq: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()