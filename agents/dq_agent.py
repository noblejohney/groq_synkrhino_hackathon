from groq_interface.groq_client import GroqClient

class DQAgent:
    def __init__(self, api_key):
        self.client = GroqClient(api_key)

    def generate_dq_rules(self, description):
        prompt = [
            {"role": "system", "content": "You're a data quality rule generator for SynkRhino."},
            {"role": "user", "content": f"Generate metadata and table-level DQ checks for: {description}"}
        ]
        return self.client.chat(prompt)
