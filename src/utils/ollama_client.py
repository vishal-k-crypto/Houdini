"""
Ollama Client for Qwen 3 Coder 480B model via Ollama Cloud
"""
import subprocess
import json
import time
from typing import Optional, List, Dict
from .logging import logger
try:
    from ..replay.execution_logger import log_llm_interaction
except ImportError:
    # Fallback if logger not available
    def log_llm_interaction(*args, **kwargs): pass


class OllamaClient:
    """
    Client for Ollama's Qwen 3 Coder 480B parameter model via cloud.
    Replaces Gemini for all agent operations.
    """
    
    def __init__(self, model_name: str = "qwen3-coder:480b-cloud", cloud_endpoint: Optional[str] = None):
        """
        Initialize Ollama client.
        
        Args:
            model_name: Model to use (default: qwen3-coder:480b-cloud for cloud 480B)
            cloud_endpoint: Optional cloud endpoint URL (for Ollama Cloud)
        """
        self.model_name = model_name
        self.cloud_endpoint = cloud_endpoint
        self._verify_installation()
    
    def _verify_installation(self):
        """Check if Ollama is available."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            logger.info(f"Ollama is available. Models: {result.stdout.strip()[:100]}")
        except FileNotFoundError:
            raise RuntimeError(
                "Ollama not found. Install it from https://ollama.ai\n"
                "Then pull the model with:\n"
                f"  ollama pull {self.model_name}"
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Ollama check returned error: {e.stderr}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict]] = None,
        retry_count: int = 3,
        temperature: float = 0.7,
        model: Optional[str] = None
    ) -> str:
        """
        Generate text using Ollama.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system instructions
            context: Optional conversation context (list of message dicts)
            retry_count: Number of retry attempts
            temperature: Sampling temperature (0.0-1.0)
            model: Optional model override
        
        Returns:
            Generated text response
        """
        model_to_use = model or self.model_name
        
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                
                # Build the request payload
                payload = {
                    "model": model_to_use,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 4096  # Max tokens
                    }
                }
                
                # Add system prompt if provided
                if system_prompt:
                    payload["system"] = system_prompt
                
                # Add context if provided
                if context:
                    payload["context"] = context
                
                # Use cloud endpoint if configured, otherwise local
                if self.cloud_endpoint:
                    cmd = [
                        "curl",
                        "-X", "POST",
                        f"{self.cloud_endpoint}/api/generate",
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps(payload)
                    ]
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                else:
                    # Local Ollama via CLI
                    cmd = ["ollama", "run", model_to_use]
                    
                    # Build full prompt with system instructions
                    full_prompt = ""
                    if system_prompt:
                        full_prompt += f"<|system|>\n{system_prompt}\n\n"
                    full_prompt += f"<|user|>\n{prompt}\n\n<|assistant|>\n"
                    
                    result = subprocess.run(
                        cmd,
                        input=full_prompt,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                
                duration = time.time() - start_time
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    
                    # Parse JSON response if using cloud endpoint
                    if self.cloud_endpoint:
                        try:
                            response_json = json.loads(output)
                            output = response_json.get("response", "")
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse JSON response from Ollama Cloud")
                    
                    if output:
                        logger.debug(f"Ollama ({model_to_use}) response time: {duration:.1f}s")
                        
                        # Log to execution logger for training data
                        log_llm_interaction(
                            component="ollama_client",
                            prompt=full_prompt if 'full_prompt' in locals() else (payload.get('system', '') + "\n\n" + prompt),
                            response=output,
                            model=model_to_use,
                            duration_ms=duration * 1000
                        )
                        
                        return output
                    else:
                        logger.warning("Empty response from Ollama")
                else:
                    logger.error(f"Ollama error (attempt {attempt+1}/{retry_count}): {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Ollama timed out (attempt {attempt+1}/{retry_count})")
            except Exception as e:
                logger.error(f"Ollama error (attempt {attempt+1}/{retry_count}): {str(e)}")
            
            # Wait before retry
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # All retries failed
        raise RuntimeError(f"Failed to get response from Ollama after {retry_count} attempts")
    
    def generate_with_history(
        self,
        prompt: str,
        history: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate with conversation history for context.
        
        Args:
            prompt: Current user prompt
            history: List of {"role": "user"/"assistant", "content": "..."} dicts
            system_prompt: Optional system instructions
            **kwargs: Additional arguments for generate()
        
        Returns:
            Generated response
        """
        # Build context-aware prompt
        context_prompt = ""
        
        # Add history
        if history:
            context_prompt += "Previous conversation:\n"
            for msg in history[-5:]:  # Last 5 messages for context
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                context_prompt += f"{role.upper()}: {content}\n"
            context_prompt += "\n"
        
        # Add current prompt
        context_prompt += f"Current request: {prompt}"
        
        return self.generate(
            context_prompt,
            system_prompt=system_prompt,
            **kwargs
        )
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> dict:
        """
        Generate and parse JSON response.
        
        Args:
            prompt: The prompt (should request JSON output)
            system_prompt: Optional system instructions
            **kwargs: Additional arguments for generate()
        
        Returns:
            Parsed JSON dict
        """
        # Ensure JSON format is requested
        if "json" not in prompt.lower():
            prompt += "\n\nRespond with valid JSON only."
        
        response = self.generate(prompt, system_prompt=system_prompt, **kwargs)
        
        # Try to extract JSON from response
        try:
            # Find JSON content between ```json and ``` or { and }
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                # Try to find JSON object
                start = response.find("{")
                end = response.rfind("}") + 1
                if start != -1 and end != 0:
                    json_str = response[start:end]
                else:
                    json_str = response
            
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response was: {response}")
            raise ValueError(f"Invalid JSON response from Ollama: {response[:200]}")


# Alias for backward compatibility with Gemini code
QwenClient = OllamaClient
