"""
Lesson Store - RAG-based storage for learned lessons using FAISS Vector Database.

This module replaces the markdown-appending approach in PromptEvolution with
a FAISS vector database for efficient semantic retrieval of relevant lessons.

Key Features:
- Store failures and their solutions as embeddings
- Retrieve top-k similar lessons before planning
- Track lesson effectiveness (which lessons actually helped)
- Prevent context window bloat by only injecting relevant lessons
"""

import json
import hashlib
import pickle
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
import numpy as np

from .logging import logger
from .embedding_client import EmbeddingClient

# Persistence directory for FAISS and metadata
LESSON_DB_DIR = Path(__file__).parent.parent.parent / "data" / "lessons_db"
LESSONS_METADATA_FILE = LESSON_DB_DIR / "lessons_metadata.json"
FAISS_INDEX_FILE = LESSON_DB_DIR / "faiss_index.pkl"


@dataclass
class Lesson:
    """A learned lesson from a failure or success."""
    id: str
    component: str              # "planner", "executor", "supervisor"
    failure_type: str           # "element_not_found", "timing_issue", etc.
    task_context: str           # The task that triggered this lesson
    problem: str                # What went wrong
    solution: str               # How to fix it
    success_count: int = 0      # Times this lesson helped
    fail_count: int = 0         # Times this lesson was retrieved but didn't help
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def effectiveness(self) -> float:
        """Calculate lesson effectiveness score."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5  # Neutral for new lessons
        return self.success_count / total
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Lesson":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            component=data["component"],
            failure_type=data["failure_type"],
            task_context=data["task_context"],
            problem=data["problem"],
            solution=data["solution"],
            success_count=data.get("success_count", 0),
            fail_count=data.get("fail_count", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
    
    def to_prompt_text(self) -> str:
        """Format lesson for prompt injection."""
        return f"• {self.failure_type}: {self.problem} → {self.solution}"


class LessonStore:
    """
    Vector database for storing and retrieving lessons using FAISS.
    
    Replaces the markdown-appending approach with semantic retrieval.
    Only the top-k most relevant lessons are injected into prompts.
    """
    
    def __init__(
        self, 
        persist_dir: Path = LESSON_DB_DIR,
        embedding_backend: str = "ollama",
        embedding_dim: int = 768  # Default for nomic-embed-text
    ):
        """
        Initialize the Lesson Store.
        
        Args:
            persist_dir: Directory for FAISS persistence
            embedding_backend: "ollama" or "gemini"
            embedding_dim: Dimension of embeddings (768 for nomic-embed-text)
        """
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.persist_dir / "lessons_metadata.json"
        self.index_file = self.persist_dir / "faiss_index.pkl"
        self.embedding_dim = embedding_dim
        
        # Initialize embedding client
        self.embedder = EmbeddingClient(backend=embedding_backend)
        
        # Lesson storage
        self.lessons: Dict[str, Lesson] = {}  # id -> Lesson
        self.id_to_idx: Dict[str, int] = {}   # id -> FAISS index position
        self.idx_to_id: Dict[int, str] = {}   # FAISS index position -> id
        
        # Initialize FAISS
        self._init_faiss()
        
        # Load existing data
        self._load()
        
    def _init_faiss(self):
        """Initialize FAISS index."""
        try:
            import faiss
            
            # Create or load index
            if self.index_file.exists():
                with open(self.index_file, 'rb') as f:
                    self.index = pickle.load(f)
            else:
                # Use IndexFlatIP for inner product (cosine similarity after normalization)
                self.index = faiss.IndexFlatIP(self.embedding_dim)
            
            self.faiss_available = True
            logger.info(f"✅ FAISS initialized with {self.index.ntotal} vectors")
            
        except ImportError:
            logger.error("FAISS not installed. Run: pip install faiss-cpu")
            self.index = None
            self.faiss_available = False
    
    def _load(self):
        """Load lessons from disk."""
        if not self.metadata_file.exists():
            return
            
        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
            
            self.lessons = {
                id_: Lesson.from_dict(lesson_data) 
                for id_, lesson_data in data.get("lessons", {}).items()
            }
            self.id_to_idx = data.get("id_to_idx", {})
            self.idx_to_id = {int(k): v for k, v in data.get("idx_to_id", {}).items()}
            
            logger.info(f"📚 Loaded {len(self.lessons)} lessons from disk")
            
        except Exception as e:
            logger.warning(f"Failed to load lessons: {e}")
    
    def _save(self):
        """Save lessons to disk."""
        try:
            # Save metadata
            data = {
                "lessons": {id_: lesson.to_dict() for id_, lesson in self.lessons.items()},
                "id_to_idx": self.id_to_idx,
                "idx_to_id": {str(k): v for k, v in self.idx_to_id.items()}
            }
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Save FAISS index
            if self.faiss_available and self.index is not None:
                with open(self.index_file, 'wb') as f:
                    pickle.dump(self.index, f)
                    
        except Exception as e:
            logger.error(f"Failed to save lessons: {e}")
    
    def _generate_lesson_id(self, problem: str, solution: str) -> str:
        """Generate a unique ID for a lesson based on content."""
        content = f"{problem}:{solution}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        """Normalize vector for cosine similarity."""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec
    
    def add_lesson(self, lesson: Lesson) -> bool:
        """
        Add a lesson to the vector database.
        
        Args:
            lesson: The lesson to store
            
        Returns:
            True if successful, False otherwise
        """
        if not self.faiss_available:
            logger.error("FAISS not initialized")
            return False
            
        try:
            # Check if already exists
            if lesson.id in self.lessons:
                # Update existing lesson
                self.lessons[lesson.id] = lesson
                self._save()
                return True
            
            # Create embedding text (combines problem and solution for better retrieval)
            embed_text = f"{lesson.task_context} {lesson.problem} {lesson.solution}"
            embedding = self.embedder.embed(embed_text)
            
            # Ensure correct dimension
            if len(embedding) != self.embedding_dim:
                # If embedding dimension doesn't match, update expected dimension
                self.embedding_dim = len(embedding)
                # Reinitialize FAISS with correct dimension
                import faiss
                self.index = faiss.IndexFlatIP(self.embedding_dim)
                self.id_to_idx = {}
                self.idx_to_id = {}
            
            # Normalize for cosine similarity
            embedding_np = self._normalize_vector(np.array([embedding], dtype=np.float32))
            
            # Add to FAISS
            idx = self.index.ntotal
            self.index.add(embedding_np)
            
            # Update mappings
            self.id_to_idx[lesson.id] = idx
            self.idx_to_id[idx] = lesson.id
            self.lessons[lesson.id] = lesson
            
            # Persist
            self._save()
            
            logger.info(f"📚 Added lesson: {lesson.failure_type} - {lesson.problem[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add lesson: {e}")
            return False
    
    def retrieve_similar(
        self, 
        task: str, 
        component: Optional[str] = None, 
        k: int = 3,
        threshold: float = 0.5
    ) -> List[Lesson]:
        """
        Retrieve top-k semantically similar lessons.
        
        Args:
            task: The current task to find lessons for
            component: Optional filter by component ("planner", "executor", etc.)
            k: Number of lessons to retrieve
            threshold: Minimum similarity threshold (0-1)
            
        Returns:
            List of similar lessons, sorted by relevance
        """
        if not self.faiss_available or self.index is None or self.index.ntotal == 0:
            return []
            
        try:
            # Generate embedding for query
            query_embedding = self.embedder.embed(task)
            
            # Ensure correct dimension
            if len(query_embedding) != self.embedding_dim:
                logger.warning(f"Embedding dimension mismatch: {len(query_embedding)} vs {self.embedding_dim}")
                return []
            
            # Normalize for cosine similarity
            query_np = self._normalize_vector(np.array([query_embedding], dtype=np.float32))
            
            # Search FAISS (get more than k to allow filtering)
            n_results = min(k * 3, self.index.ntotal)
            distances, indices = self.index.search(query_np, n_results)
            
            lessons = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < 0:  # FAISS returns -1 for invalid results
                    continue
                    
                # Convert distance to similarity (FAISS inner product is already similarity)
                similarity = float(dist)
                
                if similarity < threshold:
                    continue
                
                # Get lesson ID from index
                lesson_id = self.idx_to_id.get(int(idx))
                if lesson_id and lesson_id in self.lessons:
                    lesson = self.lessons[lesson_id]
                    
                    # Filter by component if specified
                    if component and lesson.component != component:
                        continue
                    
                    lessons.append(lesson)
                    
                    if len(lessons) >= k:
                        break
            
            return lessons
            
        except Exception as e:
            logger.error(f"Failed to retrieve lessons: {e}")
            return []
    
    def record_failure(
        self,
        component: str,
        task: str,
        error_type: str,
        error_details: str,
        suggestion: Optional[str] = None
    ) -> Optional[Lesson]:
        """
        Record a failure as a lesson.
        
        Args:
            component: Which component failed ("planner", "executor", "supervisor")
            task: The task being executed
            error_type: Type of error (e.g., "element_not_found", "timeout")
            error_details: Detailed error message
            suggestion: Optional solution suggestion
            
        Returns:
            The created Lesson, or None on failure
        """
        # Generate solution based on error type if not provided
        if not suggestion:
            suggestion = self._generate_solution(error_type, error_details)
        
        lesson = Lesson(
            id=self._generate_lesson_id(error_details, suggestion),
            component=component,
            failure_type=error_type,
            task_context=task,
            problem=error_details,
            solution=suggestion
        )
        
        if self.add_lesson(lesson):
            return lesson
        return None
    
    def _generate_solution(self, error_type: str, error_details: str) -> str:
        """Generate a default solution based on error type."""
        solutions = {
            "element_not_found": "Wait for element to appear, use broader search criteria, or verify page has loaded",
            "timeout": "Increase wait time, check network conditions, or add retry logic",
            "click_failed": "Verify element is clickable, not obscured, and coordinates are correct",
            "type_failed": "Ensure input field is focused and accepts text input",
            "navigation_failed": "Verify URL is correct and accessible, check network",
            "json_parse_error": "Use stricter JSON formatting, validate structure before parsing",
            "parse_error": "Ensure output follows the required JSON schema exactly",
            "coordinate_error": "Recalculate coordinates relative to current screen, avoid absolute positions",
            "permission_denied": "Request user to grant accessibility permissions"
        }
        return solutions.get(error_type, f"Investigate and handle: {error_type}")
    
    def mark_lesson_helpful(self, lesson_id: str):
        """Mark a lesson as helpful (successful retrieval)."""
        if lesson_id in self.lessons:
            self.lessons[lesson_id].success_count += 1
            self._save()
    
    def mark_lesson_unhelpful(self, lesson_id: str):
        """Mark a lesson as unhelpful (retrieved but didn't help)."""
        if lesson_id in self.lessons:
            self.lessons[lesson_id].fail_count += 1
            self._save()
    
    def get_prompt_context(self, task: str, component: str, k: int = 3) -> str:
        """
        Get formatted lessons for prompt injection.
        
        Args:
            task: Current task
            component: Which component's prompt to enhance
            k: Number of lessons to include
            
        Returns:
            Formatted string to inject into prompt
        """
        lessons = self.retrieve_similar(task, component, k)
        
        if not lessons:
            return ""
        
        lines = ["## Relevant Past Lessons", ""]
        for lesson in lessons:
            lines.append(lesson.to_prompt_text())
        lines.append("")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the lesson store."""
        if not self.faiss_available:
            return {"error": "FAISS not initialized"}
        
        total = len(self.lessons)
        by_component: Dict[str, int] = {}
        by_failure_type: Dict[str, int] = {}
        effective_lessons = 0
        
        for lesson in self.lessons.values():
            by_component[lesson.component] = by_component.get(lesson.component, 0) + 1
            by_failure_type[lesson.failure_type] = by_failure_type.get(lesson.failure_type, 0) + 1
            if lesson.effectiveness > 0.5:
                effective_lessons += 1
        
        return {
            "total_lessons": total,
            "faiss_vectors": self.index.ntotal if self.index else 0,
            "by_component": by_component,
            "by_failure_type": by_failure_type,
            "effective_lessons": effective_lessons,
            "avg_effectiveness": sum(l.effectiveness for l in self.lessons.values()) / max(len(self.lessons), 1)
        }
    
    def cleanup_ineffective(self, min_uses: int = 5, max_effectiveness: float = 0.2):
        """
        Remove lessons that have proven ineffective.
        
        Note: FAISS doesn't support deletion efficiently, so we rebuild the index.
        
        Args:
            min_uses: Minimum number of retrievals before considering cleanup
            max_effectiveness: Maximum effectiveness score to remove
        """
        if not self.faiss_available:
            return
        
        to_remove = []
        for lesson_id, lesson in self.lessons.items():
            total_uses = lesson.success_count + lesson.fail_count
            if total_uses >= min_uses and lesson.effectiveness <= max_effectiveness:
                to_remove.append(lesson_id)
        
        if to_remove:
            # Remove from lessons dict
            for id_ in to_remove:
                del self.lessons[id_]
            
            # Rebuild FAISS index
            self._rebuild_index()
            
            logger.info(f"🗑️ Removed {len(to_remove)} ineffective lessons")
    
    def _rebuild_index(self):
        """Rebuild FAISS index from current lessons."""
        try:
            import faiss
            
            # Create new index
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            self.id_to_idx = {}
            self.idx_to_id = {}
            
            # Re-add all lessons
            for lesson in self.lessons.values():
                embed_text = f"{lesson.task_context} {lesson.problem} {lesson.solution}"
                embedding = self.embedder.embed(embed_text)
                embedding_np = self._normalize_vector(np.array([embedding], dtype=np.float32))
                
                idx = self.index.ntotal
                self.index.add(embedding_np)
                
                self.id_to_idx[lesson.id] = idx
                self.idx_to_id[idx] = lesson.id
            
            self._save()
            logger.info(f"🔄 Rebuilt FAISS index with {self.index.ntotal} vectors")
            
        except Exception as e:
            logger.error(f"Failed to rebuild index: {e}")


# Global instance
lesson_store = LessonStore()
