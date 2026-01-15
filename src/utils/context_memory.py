"""
Context-Aware Clipboard Memory - Long-term memory for user files and resources.

This module provides intelligent context resolution for ambiguous references in tasks.
When a user says "Send the report to John," this system can recall where "report" 
typically lives based on previous successful tasks.

Key Features:
- Extract file/resource references from successful task executions
- Build semantic associations between terms and file locations
- Resolve ambiguous references like "the report", "my document", "that file"
- Learn from user's file access patterns over time
- FAISS-powered semantic search for finding relevant context
"""

import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass, field, asdict
import numpy as np

from .logging import logger

# Lazy import for embedding client (avoid circular imports)
_embedding_client = None

def _get_embedding_client():
    """Get embedding client instance (lazy loading)."""
    global _embedding_client
    if _embedding_client is None:
        from .embedding_client import EmbeddingClient
        _embedding_client = EmbeddingClient(backend="ollama")
    return _embedding_client


# Persistence paths
CONTEXT_MEMORY_DIR = Path(__file__).parent.parent.parent / "data" / "context_memory"
CONTEXT_METADATA_FILE = CONTEXT_MEMORY_DIR / "context_metadata.json"
CONTEXT_FAISS_FILE = CONTEXT_MEMORY_DIR / "context_faiss.pkl"
FEEDBACK_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "feedback_log.json"


# Common file-related keywords for extraction
FILE_KEYWORDS = [
    "file", "folder", "directory", "document", "report", "presentation",
    "spreadsheet", "image", "photo", "video", "music", "pdf", "doc",
    "txt", "csv", "xlsx", "pptx", "png", "jpg", "mp4", "mp3",
    "desktop", "downloads", "documents", "pictures", "movies", "home"
]

# Patterns for extracting file paths
PATH_PATTERNS = [
    r'(~/[\w./\-]+)',                                    # Unix home paths ~/...
    r'(/Users/\w+/[\w./\-]+)',                          # Full macOS paths
    r'((?:Desktop|Downloads|Documents|Pictures|Movies)/[\w./\-]+)',  # Common folder paths
    r'\b([\w\-]+\.(?:txt|pdf|doc|docx|xlsx|csv|png|jpg|jpeg|mp4|mp3|pptx))\b',  # Files with extensions
]

# Patterns for extracting named resources  
RESOURCE_PATTERNS = [
    r'(?:named|called)\s+["\']?([A-Za-z][\w\-]*)["\']?',   # "named X" or "called X"
    r'folder\s+["\']?([A-Za-z][\w\-]*)["\']?',             # "folder X"
]

# Words to skip when extracting resources
SKIP_WORDS = {
    "a", "an", "the", "my", "your", "this", "that", "it", "is", "are", "was", "were",
    "to", "from", "in", "on", "at", "by", "for", "with", "of", "and", "or", "but",
    "file", "folder", "document", "directory", "using", "having", "create", "open",
    "save", "send", "edit", "delete", "move", "copy", "safari", "chrome", "terminal",
    "finder", "desktop", "downloads", "documents", "pictures", "movies", "home"
}


@dataclass
class ResourceContext:
    """A learned resource context from successful tasks."""
    id: str
    resource_name: str          # Name/alias (e.g., "report", "project file")
    resource_type: str          # "file", "folder", "app", "url", "contact"
    location: str               # Path, URL, or identifier
    associated_terms: List[str] # Related terms (e.g., ["quarterly report", "Q4 report"])
    associated_actions: List[str]  # Actions performed (e.g., ["send", "open", "edit"])
    associated_contacts: List[str] # People associated (e.g., ["John", "marketing team"])
    access_count: int = 0       # Times this resource was accessed
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence: float = 0.5     # Confidence score based on usage
    source_tasks: List[str] = field(default_factory=list)  # Original tasks that created this
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ResourceContext":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            resource_name=data["resource_name"],
            resource_type=data.get("resource_type", "file"),
            location=data.get("location", ""),
            associated_terms=data.get("associated_terms", []),
            associated_actions=data.get("associated_actions", []),
            associated_contacts=data.get("associated_contacts", []),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            created_at=data.get("created_at", datetime.now().isoformat()),
            confidence=data.get("confidence", 0.5),
            source_tasks=data.get("source_tasks", [])
        )
    
    def update_access(self):
        """Update access tracking."""
        self.access_count += 1
        self.last_accessed = datetime.now().isoformat()
        # Increase confidence with usage (max 1.0)
        self.confidence = min(1.0, self.confidence + 0.05)


@dataclass
class ResolvedContext:
    """Result of context resolution for a task."""
    original_task: str
    enriched_task: str          # Task with resolved references
    resolved_references: List[Dict]  # List of {term, resource, confidence}
    suggested_files: List[str]  # File paths that might be relevant
    suggested_contacts: List[str]  # Contacts that might be relevant
    context_hints: List[str]    # Additional context hints for planner
    confidence: float           # Overall resolution confidence


class ContextMemory:
    """
    Long-term memory system for user files and resources.
    
    Learns from successful task executions to build associations between
    abstract terms (like "the report") and concrete locations.
    """
    
    def __init__(
        self,
        persist_dir: Path = CONTEXT_MEMORY_DIR,
        embedding_dim: int = 768
    ):
        """
        Initialize Context Memory.
        
        Args:
            persist_dir: Directory for persistence
            embedding_dim: Dimension of embeddings (768 for nomic-embed-text)
        """
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.persist_dir / "context_metadata.json"
        self.index_file = self.persist_dir / "context_faiss.pkl"
        self.embedding_dim = embedding_dim
        
        # Resource storage
        self.resources: Dict[str, ResourceContext] = {}  # id -> ResourceContext
        self.id_to_idx: Dict[str, int] = {}   # id -> FAISS index position
        self.idx_to_id: Dict[int, str] = {}   # FAISS index position -> id
        
        # Term associations (fast lookup)
        self.term_to_resources: Dict[str, Set[str]] = {}  # term -> set of resource ids
        
        # Initialize FAISS
        self._init_faiss()
        
        # Load existing data
        self._load()
        
        # Bootstrap from feedback log if empty
        if not self.resources:
            self._bootstrap_from_feedback()
    
    def _init_faiss(self):
        """Initialize FAISS index."""
        try:
            import faiss
            
            if self.index_file.exists():
                import pickle
                with open(self.index_file, 'rb') as f:
                    self.index = pickle.load(f)
            else:
                # Use IndexFlatIP for inner product (cosine similarity after normalization)
                self.index = faiss.IndexFlatIP(self.embedding_dim)
            
            self.faiss_available = True
            logger.debug(f"ContextMemory: FAISS initialized with {self.index.ntotal} vectors")
            
        except ImportError:
            logger.warning("FAISS not installed for context memory. Using fallback search.")
            self.index = None
            self.faiss_available = False
    
    def _load(self):
        """Load context memory from disk."""
        if not self.metadata_file.exists():
            return
            
        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
            
            self.resources = {
                id_: ResourceContext.from_dict(rc_data)
                for id_, rc_data in data.get("resources", {}).items()
            }
            self.id_to_idx = data.get("id_to_idx", {})
            self.idx_to_id = {int(k): v for k, v in data.get("idx_to_id", {}).items()}
            self.term_to_resources = {
                k: set(v) for k, v in data.get("term_to_resources", {}).items()
            }
            
            logger.info(f"📁 ContextMemory: Loaded {len(self.resources)} resource contexts")
            
        except Exception as e:
            logger.warning(f"Could not load context memory: {e}")
    
    def _save(self):
        """Save context memory to disk."""
        try:
            data = {
                "resources": {id_: rc.to_dict() for id_, rc in self.resources.items()},
                "id_to_idx": self.id_to_idx,
                "idx_to_id": {str(k): v for k, v in self.idx_to_id.items()},
                "term_to_resources": {k: list(v) for k, v in self.term_to_resources.items()}
            }
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Save FAISS index
            if self.faiss_available and self.index is not None:
                import pickle
                with open(self.index_file, 'wb') as f:
                    pickle.dump(self.index, f)
                    
        except Exception as e:
            logger.error(f"Failed to save context memory: {e}")
    
    def _generate_id(self, name: str, location: str) -> str:
        """Generate unique ID for a resource."""
        content = f"{name}:{location}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        """Normalize vector for cosine similarity."""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec
    
    def _extract_file_info(self, task: str, actions: List[str]) -> List[Dict]:
        """
        Extract file/resource information from a task and its actions.
        
        Returns list of dicts with resource info.
        """
        resources = []
        seen_names = set()  # Avoid duplicates
        combined_text = f"{task} {' '.join(actions)}"
        
        # Extract file paths (high priority - these have actual locations)
        for pattern in PATH_PATTERNS:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match else ""
                if match and len(match) > 2:
                    name = Path(match).stem if '.' in match else match.split('/')[-1]
                    if name.lower() not in seen_names and name.lower() not in SKIP_WORDS:
                        seen_names.add(name.lower())
                        # Generate terms including the resource name
                        terms = [name.lower()]
                        
                        # Add common reference terms based on name OR task context
                        task_lower = task.lower()
                        
                        if "report" in name.lower() or "report" in task_lower:
                            terms.append("report")
                            terms.append("the report")
                        if "document" in name.lower() or "document" in task_lower:
                            terms.append("document")
                            terms.append("the document")
                        if "presentation" in name.lower() or "presentation" in task_lower:
                            terms.append("presentation")
                            terms.append("the presentation")
                        if "spreadsheet" in name.lower() or "spreadsheet" in task_lower or "budget" in task_lower:
                            terms.append("spreadsheet")
                            terms.append("the spreadsheet")
                        if "proposal" in name.lower() or "proposal" in task_lower:
                            terms.append("proposal")
                            terms.append("the proposal")
                            
                        resources.append({
                            "name": name,
                            "type": "file" if '.' in match else "folder",
                            "location": match,
                            "terms": list(set(terms))  # Deduplicate
                        })
        
        # Extract named resources (e.g., "folder named jhonny")
        for pattern in RESOURCE_PATTERNS:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 1:
                    clean_match = match.strip()
                    if clean_match.lower() not in seen_names and clean_match.lower() not in SKIP_WORDS:
                        seen_names.add(clean_match.lower())
                        resources.append({
                            "name": clean_match,
                            "type": self._infer_type(clean_match, combined_text),
                            "location": "",  # Will be inferred from context
                            "terms": [clean_match.lower()]
                        })
        
        # Extract contacts (proper names - capitalized words following "to", "from", "with")
        contact_pattern = r'(?:to|from|with|message|email)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
        contact_matches = re.findall(contact_pattern, combined_text)
        for match in contact_matches:
            if match and len(match) > 1:
                clean_name = match.strip()
                # Filter out common non-name words
                if clean_name.lower() not in seen_names and clean_name.lower() not in SKIP_WORDS:
                    seen_names.add(clean_name.lower())
                    resources.append({
                        "name": clean_name,
                        "type": "contact",
                        "location": "",
                        "terms": [clean_name.lower()]
                    })
        
        return resources
    
    def _infer_type(self, name: str, context: str) -> str:
        """Infer resource type from name and context."""
        name_lower = name.lower()
        context_lower = context.lower()
        
        if any(ext in name_lower for ext in [".txt", ".doc", ".pdf", ".xlsx"]):
            return "file"
        if any(word in name_lower for word in ["folder", "directory"]):
            return "folder"
        if any(word in context_lower for word in ["email", "message", "send to", "contact"]):
            return "contact"
        if any(word in context_lower for word in ["website", "url", "http", "www"]):
            return "url"
        if any(word in name_lower for word in ["report", "document", "file", "presentation"]):
            return "file"
        
        return "file"  # Default
    
    def _extract_actions(self, task: str) -> List[str]:
        """Extract action verbs from a task."""
        action_verbs = [
            "open", "create", "save", "send", "email", "attach", "upload",
            "download", "edit", "delete", "copy", "move", "share", "print",
            "export", "import", "compress", "extract", "play", "view"
        ]
        found_actions = []
        task_lower = task.lower()
        for verb in action_verbs:
            if verb in task_lower:
                found_actions.append(verb)
        return found_actions
    
    def _bootstrap_from_feedback(self):
        """Bootstrap context memory from feedback_log.json."""
        if not FEEDBACK_LOG_FILE.exists():
            logger.debug("ContextMemory: No feedback log to bootstrap from")
            return
        
        try:
            with open(FEEDBACK_LOG_FILE, 'r') as f:
                feedback_data = json.load(f)
            
            if not isinstance(feedback_data, list):
                return
            
            # Process successful tasks
            for entry in feedback_data:
                if entry.get("success") and entry.get("task"):
                    self.learn_from_task(
                        task=entry["task"],
                        actions=entry.get("actions_taken", []),
                        success=True
                    )
            
            logger.info(f"📚 ContextMemory: Bootstrapped {len(self.resources)} resources from feedback log")
            
        except Exception as e:
            logger.warning(f"Could not bootstrap from feedback log: {e}")
    
    def learn_from_task(
        self,
        task: str,
        actions: List[str],
        success: bool,
        additional_context: Optional[Dict] = None
    ):
        """
        Learn resource associations from a completed task.
        
        Args:
            task: The task description
            actions: Actions that were taken
            success: Whether the task succeeded
            additional_context: Extra context (file paths, contacts, etc.)
        """
        if not success:
            return  # Only learn from successful tasks
        
        # Extract file/resource info
        extracted = self._extract_file_info(task, actions)
        task_actions = self._extract_actions(task)
        
        # Add additional context if provided
        if additional_context:
            if "files" in additional_context:
                for f in additional_context["files"]:
                    extracted.append({
                        "name": Path(f).stem,
                        "type": "file",
                        "location": f,
                        "terms": [Path(f).stem.lower()]
                    })
        
        # Create or update resource contexts
        for resource_info in extracted:
            resource_id = self._generate_id(
                resource_info["name"],
                resource_info.get("location", resource_info["name"])
            )
            
            if resource_id in self.resources:
                # Update existing resource
                rc = self.resources[resource_id]
                rc.update_access()
                
                # Add new terms
                for term in resource_info.get("terms", []):
                    if term not in rc.associated_terms:
                        rc.associated_terms.append(term)
                
                # Add new actions
                for action in task_actions:
                    if action not in rc.associated_actions:
                        rc.associated_actions.append(action)
                
                # Add source task
                if task not in rc.source_tasks:
                    rc.source_tasks.append(task)
                    
            else:
                # Create new resource context
                rc = ResourceContext(
                    id=resource_id,
                    resource_name=resource_info["name"],
                    resource_type=resource_info.get("type", "file"),
                    location=resource_info.get("location", ""),
                    associated_terms=resource_info.get("terms", []),
                    associated_actions=task_actions,
                    associated_contacts=[],
                    source_tasks=[task]
                )
                self.resources[resource_id] = rc
                
                # Add to FAISS index
                self._add_to_index(rc)
            
            # Update term associations
            for term in resource_info.get("terms", []):
                if term not in self.term_to_resources:
                    self.term_to_resources[term] = set()
                self.term_to_resources[term].add(resource_id)
        
        self._save()
    
    def _add_to_index(self, resource: ResourceContext):
        """Add a resource to the FAISS index."""
        if not self.faiss_available:
            return
        
        try:
            # Create searchable text from resource
            search_text = f"{resource.resource_name} {' '.join(resource.associated_terms)} {resource.location}"
            
            embedder = _get_embedding_client()
            embedding = embedder.embed(search_text)
            
            # Normalize for cosine similarity
            vec = np.array([embedding], dtype=np.float32)
            vec = self._normalize_vector(vec.flatten()).reshape(1, -1)
            
            # Add to index
            idx = self.index.ntotal
            self.index.add(vec)
            
            self.id_to_idx[resource.id] = idx
            self.idx_to_id[idx] = resource.id
            
        except Exception as e:
            logger.debug(f"Could not add resource to FAISS index: {e}")
    
    def resolve_context(self, task: str, top_k: int = 5) -> ResolvedContext:
        """
        Resolve ambiguous references in a task using learned context.
        
        Args:
            task: The user's task description
            top_k: Number of top resources to consider
            
        Returns:
            ResolvedContext with enriched task and suggestions
        """
        resolved_refs = []
        suggested_files = set()  # Use set to deduplicate
        suggested_contacts = set()  # Use set to deduplicate
        context_hints = []
        enriched_task = task
        seen_hints = set()  # Track hints to avoid duplicates
        
        # 1. Direct term matching (fast path)
        task_lower = task.lower()
        for term, resource_ids in self.term_to_resources.items():
            if term in task_lower:
                for rid in resource_ids:
                    if rid in self.resources:
                        rc = self.resources[rid]
                        resolved_refs.append({
                            "term": term,
                            "resource": rc.to_dict(),
                            "confidence": rc.confidence,
                            "match_type": "exact"
                        })
                        if rc.resource_type == "file" and rc.location:
                            suggested_files.add(rc.location)
                        if rc.resource_type == "contact":
                            suggested_contacts.add(rc.resource_name)
        
        # 2. Semantic search for ambiguous terms (slow path)
        ambiguous_terms = self._find_ambiguous_terms(task)
        
        if ambiguous_terms and self.faiss_available and self.index.ntotal > 0:
            for term in ambiguous_terms:
                similar = self._semantic_search(term, top_k=3)
                for match in similar:
                    if match["confidence"] > 0.6:  # Only high-confidence matches
                        resolved_refs.append({
                            "term": term,
                            "resource": match["resource"].to_dict(),
                            "confidence": match["confidence"],
                            "match_type": "semantic"
                        })
                        if match["resource"].resource_type == "file" and match["resource"].location:
                            suggested_files.add(match["resource"].location)
        
        # 3. Generate context hints for the planner (deduplicated)
        if resolved_refs:
            for ref in resolved_refs[:3]:  # Top 3 most relevant
                rc = ref["resource"]
                if rc.get("location"):
                    hint = f"'{ref['term']}' likely refers to: {rc['location']}"
                    if hint not in seen_hints:
                        seen_hints.add(hint)
                        context_hints.append(hint)
                    
                    # Enrich task if high confidence
                    if ref["confidence"] > 0.7 and ref["match_type"] == "exact":
                        # Add location hint to task
                        enriched_task = f"{task} (Note: '{ref['term']}' = {rc['location']})"
        
        # Calculate overall confidence
        if resolved_refs:
            avg_confidence = sum(r["confidence"] for r in resolved_refs) / len(resolved_refs)
        else:
            avg_confidence = 0.0
        
        return ResolvedContext(
            original_task=task,
            enriched_task=enriched_task,
            resolved_references=resolved_refs,
            suggested_files=list(suggested_files),  # Convert set to list
            suggested_contacts=list(suggested_contacts),  # Convert set to list
            context_hints=context_hints,
            confidence=avg_confidence
        )
    
    def _find_ambiguous_terms(self, task: str) -> List[str]:
        """Find terms in task that might need context resolution."""
        ambiguous = []
        
        # Patterns that suggest ambiguous references
        patterns = [
            r'(?:the|that|this)\s+([\w\s]+?)(?:\s+(?:file|document|report|folder|to|from))',
            r'(?:my|your)\s+([\w\s]+?)(?:\s+(?:file|document|report|folder))',
            r'(?:send|email|attach|open)\s+(?:the|that|this)?\s*([\w\s]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, task, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 2:
                    clean = match.strip().lower()
                    if clean not in ["a", "the", "my", "this", "that", "it", "file", "document"]:
                        ambiguous.append(clean)
        
        return list(set(ambiguous))
    
    def _semantic_search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search for resources semantically similar to query.
        
        Returns list of {resource, confidence} dicts.
        """
        if not self.faiss_available or self.index.ntotal == 0:
            return []
        
        try:
            embedder = _get_embedding_client()
            query_embedding = embedder.embed(query)
            
            # Normalize
            vec = np.array([query_embedding], dtype=np.float32)
            vec = self._normalize_vector(vec.flatten()).reshape(1, -1)
            
            # Search
            scores, indices = self.index.search(vec, min(top_k, self.index.ntotal))
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx in self.idx_to_id:
                    resource_id = self.idx_to_id[idx]
                    if resource_id in self.resources:
                        # Combine FAISS score with resource confidence
                        rc = self.resources[resource_id]
                        combined_conf = (score + rc.confidence) / 2
                        results.append({
                            "resource": rc,
                            "confidence": float(combined_conf)
                        })
            
            return sorted(results, key=lambda x: x["confidence"], reverse=True)
            
        except Exception as e:
            logger.debug(f"Semantic search failed: {e}")
            return []
    
    def get_recent_files(self, limit: int = 10) -> List[ResourceContext]:
        """Get recently accessed file resources."""
        file_resources = [
            rc for rc in self.resources.values()
            if rc.resource_type == "file"
        ]
        return sorted(
            file_resources,
            key=lambda x: x.last_accessed,
            reverse=True
        )[:limit]
    
    def get_frequent_contacts(self, limit: int = 10) -> List[ResourceContext]:
        """Get frequently contacted contacts."""
        contact_resources = [
            rc for rc in self.resources.values()
            if rc.resource_type == "contact"
        ]
        return sorted(
            contact_resources,
            key=lambda x: x.access_count,
            reverse=True
        )[:limit]
    
    def get_context_for_planner(self, task: str) -> str:
        """
        Generate context string to inject into planner prompt.
        
        Returns a formatted string with relevant context for the task.
        """
        resolved = self.resolve_context(task)
        
        if not resolved.context_hints and not resolved.suggested_files:
            return ""
        
        context_parts = []
        
        if resolved.context_hints:
            context_parts.append("## Resolved Context (from previous tasks)")
            for hint in resolved.context_hints[:5]:
                context_parts.append(f"- {hint}")
        
        if resolved.suggested_files:
            context_parts.append("\n## Suggested File Locations")
            for f in resolved.suggested_files[:3]:
                context_parts.append(f"- {f}")
        
        if resolved.suggested_contacts:
            context_parts.append("\n## Known Contacts")
            for c in resolved.suggested_contacts[:3]:
                context_parts.append(f"- {c}")
        
        return "\n".join(context_parts)


# Global instance
_context_memory: Optional[ContextMemory] = None


def get_context_memory() -> ContextMemory:
    """Get the global ContextMemory instance."""
    global _context_memory
    if _context_memory is None:
        _context_memory = ContextMemory()
    return _context_memory


def resolve_task_context(task: str) -> ResolvedContext:
    """Convenience function to resolve context for a task."""
    return get_context_memory().resolve_context(task)


def learn_from_successful_task(task: str, actions: List[str], context: Optional[Dict] = None):
    """Convenience function to learn from a successful task."""
    get_context_memory().learn_from_task(task, actions, success=True, additional_context=context)


def get_planner_context(task: str) -> str:
    """Get context string to inject into planner prompt."""
    return get_context_memory().get_context_for_planner(task)
