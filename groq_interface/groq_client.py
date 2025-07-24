import os
import requests
import certifi

class GroqClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def chat(self, messages, model="llama3-70b-8192"):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages
        }
        response = requests.post(self.url, headers=headers, json=payload, verify=False)
        return response.json()["choices"][0]["message"]["content"]
