import time
from cohere.errors import TooManyRequestsError

async def embed_query(self, text: str, max_retries: int = 3) -> List[float]:
    """Embed a single query with retry logic."""
    for attempt in range(max_retries):
        try:
            response = self._client.embed(
                texts=[text],
                model=self._model,
                input_type="search_query",
            )
            return response.embeddings[0]
        except TooManyRequestsError:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 30  # 30s, 60s, 90s
                print(f"⏳ Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise