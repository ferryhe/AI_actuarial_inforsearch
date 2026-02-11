#!/usr/bin/env python3
"""
Unit tests for semantic chunking module.

Tests the structure-aware chunking for legal and academic documents.
"""

import unittest
from ai_actuarial.rag.semantic_chunking import SemanticChunker, Chunk
from ai_actuarial.rag.exceptions import ChunkingException


class TestSemanticChunker(unittest.TestCase):
    """Test semantic chunking functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.chunker = SemanticChunker(
            max_tokens=800,
            min_tokens=100,
            preserve_headers=True,
            preserve_citations=True,
            include_hierarchy=True
        )
    
    def test_empty_content_raises_exception(self):
        """Test that empty content raises ChunkingException."""
        with self.assertRaises(ChunkingException):
            self.chunker.chunk_document("")
        
        with self.assertRaises(ChunkingException):
            self.chunker.chunk_document("   \n   ")
    
    def test_simple_section_chunking(self):
        """Test chunking by markdown sections."""
        content = """# Document Title

## Section 1

This is the first section with some content that explains the topic.
It has multiple sentences and paragraphs.

This is another paragraph in section 1.

## Section 2

This is the second section with different content.
It also has multiple paragraphs.

### Subsection 2.1

This is a subsection under section 2.
It contains more detailed information.

## Section 3

Final section with concluding remarks.
"""
        chunks = self.chunker.chunk_document(content)
        
        # Should create multiple chunks based on sections
        self.assertGreater(len(chunks), 0)
        
        # Each chunk should have required attributes
        for chunk in chunks:
            self.assertIsInstance(chunk, Chunk)
            self.assertIsInstance(chunk.content, str)
            self.assertIsInstance(chunk.token_count, int)
            self.assertGreaterEqual(chunk.token_count, 0)
            self.assertIsInstance(chunk.chunk_index, int)
    
    def test_section_hierarchy_tracking(self):
        """Test that section hierarchy is tracked correctly."""
        content = """# Main Title

## Chapter 1

Content of chapter 1.

### Section 1.1

Content of section 1.1.

#### Subsection 1.1.1

Content of subsection 1.1.1.

## Chapter 2

Content of chapter 2.
"""
        chunks = self.chunker.chunk_document(content)
        
        # Check that hierarchy is tracked
        hierarchies = [c.section_hierarchy for c in chunks if c.section_hierarchy]
        self.assertGreater(len(hierarchies), 0)
        
        # Should have nested hierarchy
        has_nested = any(' > ' in h for h in hierarchies if h)
        self.assertTrue(has_nested, "Should have nested section hierarchy")
    
    def test_paragraph_chunking_fallback(self):
        """Test paragraph-based chunking for documents without clear sections."""
        content = """This is a document without headers.

It has multiple paragraphs of content that need to be chunked appropriately.

Each paragraph contains information about different topics.

The chunker should handle this by splitting on paragraph boundaries while respecting token limits.

This ensures semantic coherence is maintained even without explicit section markers.

Additional paragraphs continue the document with more information and context.
"""
        chunks = self.chunker.chunk_document(content)
        
        # Should create chunks even without headers
        self.assertGreater(len(chunks), 0)
        
        # Chunks should respect token limits
        for chunk in chunks:
            self.assertLessEqual(chunk.token_count, self.chunker.max_tokens)
    
    def test_oversized_section_splitting(self):
        """Test that oversized sections are split appropriately."""
        # Create a section with lots of content
        long_paragraph = " ".join([f"Sentence {i} with some content." for i in range(200)])
        content = f"""## Large Section

{long_paragraph}

This is additional content after the long paragraph.
"""
        chunks = self.chunker.chunk_document(content)
        
        # Should split the oversized section
        self.assertGreater(len(chunks), 1)
        
        # Each chunk should be within limits
        for chunk in chunks:
            self.assertLessEqual(chunk.token_count, self.chunker.max_tokens)
    
    def test_token_counting(self):
        """Test token counting functionality."""
        text = "This is a test sentence."
        token_count = self.chunker.count_tokens(text)
        
        self.assertGreater(token_count, 0)
        self.assertLess(token_count, 20)  # Should be reasonable for short sentence
    
    def test_citation_preservation(self):
        """Test that citations are preserved in chunks."""
        content = """## Research Section

According to Smith et al. (2023), the methodology shows promising results[1].

Recent studies (Jones, 2024; Brown & White, 2023) support this conclusion.

### References

[1] Smith, J., et al. (2023). Research Paper Title. Journal Name.
"""
        chunks = self.chunker.chunk_document(content)
        
        # Check that citation formats are present in chunks
        all_content = ' '.join(chunk.content for chunk in chunks)
        self.assertIn('(2023)', all_content)
        self.assertIn('[1]', all_content)
    
    def test_minimum_token_threshold(self):
        """Test that chunks meet minimum token requirements."""
        content = """## Section 1

Short content.

## Section 2

Another short section.

## Section 3

This section has more substantial content that definitely exceeds the minimum token threshold requirement.
It has multiple sentences and provides enough context to be meaningful.
"""
        chunks = self.chunker.chunk_document(content)
        
        # Most chunks should meet minimum (allowing some flexibility)
        chunks_meeting_min = sum(1 for c in chunks if c.token_count >= self.chunker.min_tokens)
        
        # At least some chunks should meet the minimum
        self.assertGreater(chunks_meeting_min, 0)
    
    def test_metadata_propagation(self):
        """Test that metadata is propagated to chunks."""
        content = """## Section 1

Content with metadata.

## Section 2

More content.
"""
        metadata = {
            "document_title": "Test Document",
            "author": "Test Author",
            "date": "2024-02-11"
        }
        
        chunks = self.chunker.chunk_document(content, metadata)
        
        # Each chunk should have metadata
        for chunk in chunks:
            self.assertIsNotNone(chunk.metadata)
            self.assertEqual(chunk.metadata.get("document_title"), "Test Document")


class TestChunkDataclass(unittest.TestCase):
    """Test Chunk dataclass."""
    
    def test_chunk_creation(self):
        """Test creating a Chunk instance."""
        chunk = Chunk(
            content="Test content",
            token_count=10,
            chunk_index=0,
            section_hierarchy="Section 1 > Subsection 1.1",
            metadata={"key": "value"}
        )
        
        self.assertEqual(chunk.content, "Test content")
        self.assertEqual(chunk.token_count, 10)
        self.assertEqual(chunk.chunk_index, 0)
        self.assertEqual(chunk.section_hierarchy, "Section 1 > Subsection 1.1")
        self.assertEqual(chunk.metadata["key"], "value")
    
    def test_chunk_optional_fields(self):
        """Test Chunk with optional fields as None."""
        chunk = Chunk(
            content="Test",
            token_count=5,
            chunk_index=0
        )
        
        self.assertIsNone(chunk.section_hierarchy)
        self.assertIsNone(chunk.metadata)


if __name__ == '__main__':
    unittest.main()
