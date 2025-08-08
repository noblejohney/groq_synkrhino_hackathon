import os
import requests
from dotenv import load_dotenv

load_dotenv()  # loads .env if present

class GroqClient:
    def __init__(self, model: str = "llama3-70b-8192"):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Missing GROQ_API_KEY env variable")

        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = model

    def chat(self, messages):
        """
        Send a chat completion request to Groq.

        Parameters
        ----------
        messages : list[dict]
            The conversation: each dict has "role" and "content".

        Returns
        -------
        str
            The assistant's reply.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "messages": messages}

        # NOTE: We let requests perform SSL verification by default.
        # (If you really have to skip cert validation, set `verify=False`,
        # but that’s not recommended for production.)
        resp = requests.post(self.url, headers=headers, json=payload, timeout=30, verify=False)

        resp.raise_for_status()          # Raise an exception for non‑2xx
        data = resp.json()
        return data["choices"][0]["message"]["content"]