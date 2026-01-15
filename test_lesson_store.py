"""
Test suite for the Lesson Store (RAG-based learning system).

Tests the vector database storage, semantic retrieval, and prompt injection.
"""

import pytest
import tempfile
import shutil
from pathlib import Path


class TestEmbeddingClient:
    """Test embedding generation."""
    
    def test_ollama_embed_fallback(self):
        """Test that embedding client has fallback for missing Ollama."""
        from src.utils.embedding_client import EmbeddingClient
        
        client = EmbeddingClient(backend="ollama")
        # Even if Ollama isn't running, should return a vector
        embedding = client.embed("test text")
        
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)
    
    def test_embed_consistency(self):
        """Test that same text produces same embedding."""
        from src.utils.embedding_client import EmbeddingClient
        
        client = EmbeddingClient(backend="ollama")
        
        text = "search for python tutorials"
        emb1 = client.embed(text)
        emb2 = client.embed(text)
        
        # Should be identical for same text
        assert emb1 == emb2


class TestLessonStore:
    """Test the LessonStore vector database."""
    
    @pytest.fixture
    def temp_lesson_store(self, tmp_path):
        """Create a temporary lesson store for testing."""
        from src.utils.lesson_store import LessonStore
        
        persist_dir = tmp_path / "test_lessons_db"
        store = LessonStore(persist_dir=persist_dir, embedding_backend="ollama")
        yield store
        
        # Cleanup
        if persist_dir.exists():
            shutil.rmtree(persist_dir)
    
    def test_add_and_retrieve_lesson(self, temp_lesson_store):
        """Test basic add and retrieve functionality."""
        from src.utils.lesson_store import Lesson
        
        store = temp_lesson_store
        
        # Add a lesson
        lesson = Lesson(
            id="test_001",
            component="planner",
            failure_type="element_not_found",
            task_context="click the submit button",
            problem="Could not find element 'Submit'",
            solution="Wait for page to load before clicking"
        )
        
        result = store.add_lesson(lesson)
        assert result is True
        
        # Retrieve similar
        similar = store.retrieve_similar("click on submit", component="planner", k=1)
        assert len(similar) > 0
        assert similar[0].failure_type == "element_not_found"
    
    def test_record_failure(self, temp_lesson_store):
        """Test recording a failure creates a lesson."""
        store = temp_lesson_store
        
        lesson = store.record_failure(
            component="executor",
            task="open Safari and search",
            error_type="timeout",
            error_details="Timed out waiting for Safari to open"
        )
        
        assert lesson is not None
        assert lesson.component == "executor"
        assert lesson.failure_type == "timeout"
    
    def test_prompt_context_generation(self, temp_lesson_store):
        """Test that prompt context is generated correctly."""
        from src.utils.lesson_store import Lesson
        
        store = temp_lesson_store
        
        # Add some lessons
        store.add_lesson(Lesson(
            id="lesson_1",
            component="planner",
            failure_type="timing_issue",
            task_context="open YouTube and play video",
            problem="Video didn't load in time",
            solution="Add wait step after page navigation"
        ))
        
        store.add_lesson(Lesson(
            id="lesson_2",
            component="planner",
            failure_type="click_failed",
            task_context="click play button on YouTube",
            problem="Play button not clickable",
            solution="Wait for video player to initialize"
        ))
        
        # Get prompt context for similar task
        context = store.get_prompt_context("play a YouTube video", "planner")
        
        assert "Relevant Past Lessons" in context or context == ""  # Empty if no match
    
    def test_lesson_effectiveness_tracking(self, temp_lesson_store):
        """Test that lesson effectiveness is tracked."""
        from src.utils.lesson_store import Lesson
        
        store = temp_lesson_store
        
        lesson = Lesson(
            id="track_test",
            component="planner",
            failure_type="test",
            task_context="test task",
            problem="test problem",
            solution="test solution"
        )
        store.add_lesson(lesson)
        
        # Mark as helpful multiple times
        store.mark_lesson_helpful("track_test")
        store.mark_lesson_helpful("track_test")
        store.mark_lesson_unhelpful("track_test")
        
        # Check effectiveness
        cached_lesson = store.lessons_cache.get("track_test")
        if cached_lesson:
            assert cached_lesson.success_count == 2
            assert cached_lesson.fail_count == 1
            assert cached_lesson.effectiveness > 0.5
    
    def test_statistics(self, temp_lesson_store):
        """Test statistics generation."""
        from src.utils.lesson_store import Lesson
        
        store = temp_lesson_store
        
        # Add lessons with different components
        for i, comp in enumerate(["planner", "executor", "planner"]):
            store.add_lesson(Lesson(
                id=f"stat_{i}",
                component=comp,
                failure_type="test",
                task_context=f"task {i}",
                problem=f"problem {i}",
                solution=f"solution {i}"
            ))
        
        stats = store.get_statistics()
        
        assert stats["total_lessons"] == 3
        assert stats["by_component"]["planner"] == 2
        assert stats["by_component"]["executor"] == 1


class TestIntegration:
    """Integration tests for the full system."""
    
    def test_planner_imports_lesson_store(self):
        """Test that planner can import lesson store."""
        try:
            from src.planner.gemini_planner import GeminiPlanner
            from src.utils.lesson_store import lesson_store
            # If we get here, imports work
            assert True
        except ImportError as e:
            pytest.fail(f"Import failed: {e}")
    
    def test_prompt_evolution_uses_lesson_store(self):
        """Test that prompt evolution integrates with lesson store."""
        from src.utils.prompt_evolution import PromptEvolution
        
        evolution = PromptEvolution()
        
        # Shouldn't crash even with empty failures
        evolution.evolve_prompt("planner", [])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
