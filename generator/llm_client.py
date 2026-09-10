import sys
import dynamic_config

class LlmClient:
    def __init__(self):
        pass
    def run_prompt(self, prompt):
        pass

if __name__ == "__main__":
    client = dynamic_config.get_client()
    print('enter prompt and close stdin:')
    client.run_prompt(sys.stdin.read())
    
