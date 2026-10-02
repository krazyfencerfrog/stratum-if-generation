import sys


class LlmCallError(RuntimeError):
    """A model call failed in transport (server unreachable, HTTP error,
    idle timeout, connection dropped). Carries whatever had streamed before
    the failure so the caller can save the partial trace."""

    def __init__(self, message, thinking='', response='', http_status=None):
        super().__init__(message)
        self.thinking = thinking
        self.response = response
        self.http_status = http_status


class LlmClient:
    def __init__(self):
        pass

    def run_prompt(self, prompt, **kwargs):
        """Returns (thinking, response).

        The pipeline passes these keyword arguments; a client may honor any
        of them and must ignore the ones it does not know:
          think=False        run without a reasoning trace
          format=<schema>    a JSON schema the response must match
          options={...}      sampler settings for this call
          limits={...}       max_thinking_bytes / max_response_bytes /
                             max_seconds / num_predict circuit breakers
        A client that enforces limits, or that knows token counts, reports
        them in self.last_call (see ollama_client.py); the pipeline reads
        that attribute if it exists."""
        pass


if __name__ == "__main__":
    import dynamic_config
    client = dynamic_config.get_client()
    print('enter prompt and close stdin:')
    client.run_prompt(sys.stdin.read())
