from agents.dq_agent import DQAgent
from synkrhino_integration.config_parser import parse_mapping_file
import os

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Now you can access them
groq_key = os.getenv("GROQ_API_KEY")
print("Groq API Key:", groq_key)


if __name__ == "__main__":
    groq_key = os.getenv("GROQ_API_KEY")
    agent = DQAgent(groq_key)

    mapping = parse_mapping_file("data/sample_mapping.json")
    prompt_input = f"Validate mappings between {mapping['source_system']} and {mapping['target_system']}"
    
    dq_suggestions = agent.generate_dq_rules(prompt_input)
    print("Generated DQ Rules:\n", dq_suggestions)
