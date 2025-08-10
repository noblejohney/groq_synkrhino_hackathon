import os, requests, certifi
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class GroqREST:
    def __init__(self, model="openai/gpt-oss-120b", temperature=0.0, timeout=15, retries=2, pool=20):
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not set")

        self.model = model
        self.temperature = temperature
        self.url = "https://api.groq.com/openai/v1/chat/completions"

        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
            "Connection": "keep-alive",
        })
        retry = Retry(total=retries, backoff_factor=0.5,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["POST"])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=pool, pool_maxsize=pool)
        self.s.mount("https://", adapter)
        self.timeout = timeout

    def chat(self, messages, max_tokens=None):
        payload = {"model": self.model, "temperature": self.temperature, "messages": messages}
        print(payload,'payload----->>>')
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        r = self.s.post(self.url, json=payload, timeout=self.timeout, verify=False)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
