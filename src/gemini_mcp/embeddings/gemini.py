import time
import os
import logging
from typing import List, Any
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# The brand new embedding model from Google
EMBEDDING_MODEL = "gemini-embedding-2-preview"


class GeminiEmbeddingClient:
    def __init__(self, api_key: str = None):
        """
        Initializes the Gemini client. If api_key is not provided,
        it attempts to read from the GEMINI_API_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")

        # Initialize the new google-genai SDK client
        self.client = genai.Client(api_key=self.api_key)

    def embed_items(
        self,
        items: List[Any],
        task_type: str = "RETRIEVAL_DOCUMENT",
        output_dimensionality: int = 768,
    ) -> List[List[float]]:
        """
        Sends a batch of items (strings, or multimodality bytes represented as types.Part)
        to Gemini Embedding 2.
        Leverages specific `task_type` and Matryoshka Representation Learning (MRL) dimensions.
        """
        if not items:
            return []

        try:
            embeddings = []

            # Exponential backoff for API rate limits (HTTP 429) - robust enough for TPM limits
            max_retries = 5
            response = None

            for attempt in range(max_retries):
                try:
                    # Pass advanced configuration for optimal vector accuracy
                    response = self.client.models.embed_content(
                        model=EMBEDDING_MODEL,
                        contents=items,
                        config=types.EmbedContentConfig(
                            task_type=task_type,
                            output_dimensionality=output_dimensionality,
                        ),
                    )
                    break  # Success
                except Exception as e:
                    error_msg = str(e).lower()
                    if (
                        "429" in error_msg
                        or "too many" in error_msg
                        or "resource exhausted" in error_msg
                        or "quota" in error_msg
                    ):
                        if attempt < max_retries - 1:
                            # Base 5 seconds: 5s, 10s, 20s, 40s. Wait out the 1-minute bucket.
                            wait_time = (2**attempt) * 5
                            logger.warning(
                                f"Rate limited by Gemini API. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}..."
                            )
                            time.sleep(wait_time)
                        else:
                            raise e
                    else:
                        raise e

            if response and response.embeddings:
                for emb in response.embeddings:
                    embeddings.append(emb.values)

            return embeddings

        except Exception as e:
            logger.error(f"Error calling Gemini Embedding 2: {e}")
            raise

    def embed_query(self, query: str) -> List[float]:
        """
        Embeds a single semantic search query utilizing the 'RETRIEVAL_QUERY' task type.
        """
        res = self.embed_items([query], task_type="RETRIEVAL_QUERY")
        if res:
            return res[0]
        return []
