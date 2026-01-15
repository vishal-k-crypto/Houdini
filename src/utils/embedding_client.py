"""
Embedding Client - Generate embeddings using Ollama or Gemini.

Provides a unified interface for generating text embeddings for the Lesson Store.
"""

import json
import subprocess
from typing import List, Optional
from .logging import logger


class EmbeddingClient:
    """Generate embeddings using Ollama or Gemini."""
    
    def __init__(self, backend: str = "ollama", model: Optional[str] = None):
        """
        Initialize embedding client.
        
        Args:
            backend: "ollama" or "gemini"
            model: Model to use (defaults: ollama=nomic-embed-text, gemini=text-embedding-004)
        """
        self.backend = backend
        self.model = model or self._default_model()
        self._dimension = None
        
    def _default_model(self) -> str:
        """Get default model for the backend."""
        if self.backend == "ollama":
            return "nomic-embed-text"
        elif self.backend == "gemini":
            return "text-embedding-004"
        return "nomic-embed-text"
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension (needed for ChromaDB)."""
        if self._dimension is None:
            # Generate a test embedding to get dimension
            test_embedding = self.embed("test")
            self._dimension = len(test_embedding)
        return self._dimension
        
    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if self.backend == "ollama":
            return self._embed_ollama(text)
        elif self.backend == "gemini":
            return self._embed_gemini(text)
        else:
            raise ValueError(f"Unknown embedding backend: {self.backend}")
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        # For now, process one at a time (can be optimized later)
        return [self.embed(text) for text in texts]
            
    def _embed_ollama(self, text: str) -> List[float]:
        """
        Use Ollama's embedding API.
        
        Uses the nomic-embed-text model by default (768 dimensions).
        """
        try:
            # Use subprocess to call ollama CLI for embeddings
            result = subprocess.run(
                ["ollama", "embeddings", self.model, text],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                # Try the REST API approach
                return self._embed_ollama_api(text)
                
            # Parse output
            output = result.stdout.strip()
            if output:
                return json.loads(output)
            return self._embed_ollama_api(text)
            
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Ollama CLI failed: {e}, trying API")
            return self._embed_ollama_api(text)
    
    def _embed_ollama_api(self, text: str) -> List[float]:
        """Use Ollama's REST API for embeddings."""
        import urllib.request
        import urllib.error
        
        url = "http://localhost:11434/api/embeddings"
        data = json.dumps({
            "model": self.model,
            "prompt": text
        }).encode('utf-8')
        
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("embedding", [])
        except urllib.error.URLError as e:
            logger.error(f"Ollama API error: {e}")
            # Return zero vector as fallback (dimension 768 for nomic-embed-text)
            return [0.0] * 768
            
    def _embed_gemini(self, text: str) -> List[float]:
        """
        Use Gemini's embedding API.
        
        Requires GOOGLE_API_KEY environment variable.
        """
        try:
            from google import genai
            import os
            
            client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
            result = client.models.embed_content(
                model=f"models/{self.model}",
                contents=text
            )
            return result.embeddings[0].values
            
        except ImportError:
            logger.error("google-genai package not installed")
            return [0.0] * 768
        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            return [0.0] * 768


# Default client instance (uses Ollama)
embedding_client = EmbeddingClient(backend="ollama")
