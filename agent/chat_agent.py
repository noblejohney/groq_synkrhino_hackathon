from groq_interface.groq_client import GroqClient
from synkrhino_interface.dq_executor import SynkRhinoActions

class SynkRhinoChatAgent:
    def __init__(self):
        self.llm = GroqClient()
        self.engine = SynkRhinoActions()

    def process(self, user_input):
        prompt = [
            {"role": "system", "content": "You are a SynkRhino DQ agent. Classify the query and suggest the right action."},
            {"role": "user", "content": user_input}
        ]
        action = self.llm.chat(prompt)

        if "null" in action.lower():
            return self.engine.run_null_check()
        elif "row count" in action.lower():
            return self.engine.run_row_count()
        elif "summary" in action.lower() or "failure" in action.lower():
            result = self.engine.get_validation_results()
            return self.llm.chat([
                {"role": "system", "content": "Summarize this DQ result in human-friendly language."},
                {"role": "user", "content": result}
            ])
        else:
            return f"❌ Action not recognized.\n\n🧠 Groq's Suggestion: {action}"
