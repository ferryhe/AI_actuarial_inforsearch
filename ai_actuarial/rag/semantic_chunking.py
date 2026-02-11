"""
Semantic chunking for legal and academic documents.

This module implements structure-aware chunking that preserves:
- Document hierarchy (sections, subsections)
- Citations and references
- Tables and lists
- Cross-references

Priority order:
1. Section-based chunking (preserve markdown headers)
2. Paragraph-based chunking (maintain semantic boundaries)
3. Sentence-based chunking (fallback for oversized content)
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import tiktoken

from ai_actuarial.rag.exceptions import ChunkingException


@dataclass
class Chunk:
    """Represents a semantic chunk of text."""
    content: str
    token_count: int
    chunk_index: int
    section_hierarchy: Optional[str] = None  # e.g., "Article 5 > Section 2.1"
    metadata: Optional[Dict[str, Any]] = None


class SemanticChunker:
    """
    Semantic chunker tailored for legal and academic documents.
    Preserves document structure and meaning.
    """
    
    def __init__(
        self,
        max_tokens: int = 800,
        min_tokens: int = 100,
        preserve_headers: bool = True,
        preserve_citations: bool = True,
        include_hierarchy: bool = True,
        model: str = "gpt-4"
    ):
        """
        Initialize semantic chunker.
        
        Args:
            max_tokens: Maximum tokens per chunk
            min_tokens: Minimum tokens per chunk
            preserve_headers: Whether to preserve markdown headers
            preserve_citations: Whether to keep citations intact
            include_hierarchy: Whether to add parent section context
            model: Tokenizer model to use
        """
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.preserve_headers = preserve_headers
        self.preserve_citations = preserve_citations
        self.include_hierarchy = include_hierarchy
        
        try:
            self.tokenizer = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to cl100k_base (GPT-4 encoding)
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def chunk_document(self, markdown_content: str, metadata: Optional[Dict[str, Any]] = None) -> List[Chunk]:
        """
        Chunk a markdown document using semantic structure.
        
        Args:
            markdown_content: Markdown content to chunk
            metadata: Optional metadata about the document
            
        Returns:
            List of semantic chunks
        """
        if not markdown_content or not markdown_content.strip():
            raise ChunkingException("Cannot chunk empty content")
        
        metadata = metadata or {}
        chunks = []
        
        # Strategy 1: Try section-based chunking
        section_chunks = self._chunk_by_sections(markdown_content, metadata)
        
        # Check if section chunks are reasonable
        if section_chunks and self._are_chunks_valid(section_chunks):
            chunks = section_chunks
        else:
            # Strategy 2: Fall back to paragraph-based chunking
            chunks = self._chunk_by_paragraphs(markdown_content, metadata)
        
        # Validate final chunks
        if not chunks:
            raise ChunkingException("Failed to create any chunks from content")
        
        return chunks
    
    def _chunk_by_sections(self, content: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk content by markdown sections (headers).
        
        Preserves document hierarchy and structure.
        """
        chunks = []
        
        # Split by headers (##, ###, ####, etc.)
        # Pattern matches: ## Title, ### Subtitle, etc.
        header_pattern = r'^(#{1,6})\s+(.+)$'
        
        lines = content.split('\n')
        current_section = []
        current_hierarchy = []
        current_header_level = 0
        chunk_index = 0
        
        for line in lines:
            header_match = re.match(header_pattern, line)
            
            if header_match and self.preserve_headers:
                # Found a header - process previous section if exists
                if current_section:
                    section_text = '\n'.join(current_section).strip()
                    if section_text:
                        token_count = self.count_tokens(section_text)
                        
                        # If section is too large, split it further
                        if token_count > self.max_tokens:
                            # Split by paragraphs within this section
                            sub_chunks = self._chunk_by_paragraphs(section_text, metadata)
                            for sub_chunk in sub_chunks:
                                sub_chunk.chunk_index = chunk_index
                                sub_chunk.section_hierarchy = ' > '.join(current_hierarchy) if current_hierarchy else None
                                chunks.append(sub_chunk)
                                chunk_index += 1
                            current_section = []
                        elif token_count >= self.min_tokens:
                            # Section is good size
                            chunk = Chunk(
                                content=section_text,
                                token_count=token_count,
                                chunk_index=chunk_index,
                                section_hierarchy=' > '.join(current_hierarchy) if current_hierarchy else None,
                                metadata=metadata.copy()
                            )
                            chunks.append(chunk)
                            chunk_index += 1
                            current_section = []
                        # If too small, it will be combined with next section
                        # by keeping it in current_section and not emitting a chunk yet.
                
                # Update hierarchy
                header_level = len(header_match.group(1))
                header_title = header_match.group(2).strip()
                
                # Adjust hierarchy based on header level
                if header_level <= current_header_level or not current_hierarchy:
                    # Same level or going up - replace at this level
                    current_hierarchy = current_hierarchy[:header_level-1]
                
                current_hierarchy.append(header_title)
                current_header_level = header_level
                
                # Add header to current section
                current_section.append(line)
            else:
                # Regular content line
                current_section.append(line)
        
        # Process final section
        if current_section:
            section_text = '\n'.join(current_section).strip()
            if section_text:
                token_count = self.count_tokens(section_text)
                
                if token_count > self.max_tokens:
                    sub_chunks = self._chunk_by_paragraphs(section_text, metadata)
                    for sub_chunk in sub_chunks:
                        sub_chunk.chunk_index = chunk_index
                        sub_chunk.section_hierarchy = ' > '.join(current_hierarchy) if current_hierarchy else None
                        chunks.append(sub_chunk)
                        chunk_index += 1
                elif token_count >= self.min_tokens or (token_count > 0 and not chunks):
                    # Emit if valid size OR if it's the only/last content (don't lose data)
                    chunk = Chunk(
                        content=section_text,
                        token_count=token_count,
                        chunk_index=chunk_index,
                        section_hierarchy=' > '.join(current_hierarchy) if current_hierarchy else None,
                        metadata=metadata.copy()
                    )
                    chunks.append(chunk)
        
        return chunks
    
    def _chunk_by_paragraphs(self, content: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk content by paragraphs.
        
        Used for sections that are too large or when section-based chunking fails.
        """
        chunks = []
        
        # Split by double newlines (paragraph boundaries)
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_chunk_text = []
        current_tokens = 0
        chunk_index = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_tokens = self.count_tokens(para)
            
            # If paragraph alone exceeds max, split by sentences
            if para_tokens > self.max_tokens:
                # First, save current chunk if exists
                if current_chunk_text:
                    chunk_text = '\n\n'.join(current_chunk_text)
                    chunks.append(Chunk(
                        content=chunk_text,
                        token_count=current_tokens,
                        chunk_index=chunk_index,
                        metadata=metadata.copy()
                    ))
                    chunk_index += 1
                    current_chunk_text = []
                    current_tokens = 0
                
                # Split oversized paragraph by sentences
                sentence_chunks = self._chunk_by_sentences(para, metadata, chunk_index)
                chunks.extend(sentence_chunks)
                chunk_index += len(sentence_chunks)
                continue
            
            # Check if adding this paragraph exceeds limit
            if current_tokens + para_tokens > self.max_tokens and current_chunk_text:
                # Save current chunk
                chunk_text = '\n\n'.join(current_chunk_text)
                chunks.append(Chunk(
                    content=chunk_text,
                    token_count=current_tokens,
                    chunk_index=chunk_index,
                    metadata=metadata.copy()
                ))
                chunk_index += 1
                current_chunk_text = []
                current_tokens = 0
            
            # Add paragraph to current chunk
            current_chunk_text.append(para)
            current_tokens += para_tokens
        
        # Save final chunk
        if current_chunk_text:
            chunk_text = '\n\n'.join(current_chunk_text)
            token_count = self.count_tokens(chunk_text)
            if token_count >= self.min_tokens or not chunks:  # Include if meets min or is only chunk
                chunks.append(Chunk(
                    content=chunk_text,
                    token_count=token_count,
                    chunk_index=chunk_index,
                    metadata=metadata.copy()
                ))
        
        return chunks
    
    def _chunk_by_sentences(self, text: str, metadata: Dict[str, Any], start_index: int = 0) -> List[Chunk]:
        """
        Chunk text by sentences (fallback for oversized paragraphs).
        """
        chunks = []
        
        # Simple sentence split (can be enhanced with spaCy/NLTK)
        # Split on ., !, ? followed by space and capital letter or end of string
        sentences = re.split(r'([.!?])\s+(?=[A-Z]|$)', text)
        
        # Reconstruct sentences with punctuation
        reconstructed = []
        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                reconstructed.append(sentences[i] + sentences[i+1])
            else:
                reconstructed.append(sentences[i])
        
        current_chunk_text = []
        current_tokens = 0
        chunk_index = start_index
        
        for sentence in reconstructed:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            sentence_tokens = self.count_tokens(sentence)
            
            # Check if adding this sentence exceeds limit
            if current_tokens + sentence_tokens > self.max_tokens and current_chunk_text:
                # Save current chunk
                chunk_text = ' '.join(current_chunk_text)
                chunks.append(Chunk(
                    content=chunk_text,
                    token_count=current_tokens,
                    chunk_index=chunk_index,
                    metadata=metadata.copy()
                ))
                chunk_index += 1
                current_chunk_text = []
                current_tokens = 0
            
            # Add sentence to current chunk
            current_chunk_text.append(sentence)
            current_tokens += sentence_tokens
        
        # Save final chunk
        if current_chunk_text:
            chunk_text = ' '.join(current_chunk_text)
            chunks.append(Chunk(
                content=chunk_text,
                token_count=self.count_tokens(chunk_text),
                chunk_index=chunk_index,
                metadata=metadata.copy()
            ))
        
        return chunks
    
    def _are_chunks_valid(self, chunks: List[Chunk]) -> bool:
        """Check if chunks meet quality criteria."""
        if not chunks:
            return False
        
        # Check if most chunks are within reasonable size
        valid_count = sum(
            1 for chunk in chunks 
            if self.min_tokens <= chunk.token_count <= self.max_tokens
        )
        
        # At least 70% should be within range
        return valid_count / len(chunks) >= 0.7
