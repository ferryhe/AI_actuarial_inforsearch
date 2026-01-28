"""Document categorizer for classifying documents into categories."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DocumentCategorizer:
    """Categorizes documents based on keywords and content."""
    
    def __init__(self, categories: dict[str, list[str]]):
        """Initialize document categorizer.
        
        Args:
            categories: Dictionary mapping category names to keyword lists
        """
        self.categories = categories
    
    def categorize(
        self,
        text: str,
        title: str = "",
        keywords: list[str] | None = None,
    ) -> str:
        """Categorize a document based on content and keywords.
        
        Args:
            text: Document text content
            title: Document title
            keywords: Extracted keywords
            
        Returns:
            Category name, or empty string if no match
        """
        # Combine all searchable content
        searchable = f"{title} {text}".lower()
        if keywords:
            searchable += " " + " ".join(keywords).lower()
        
        # Score each category
        category_scores: dict[str, int] = {}
        
        for category_name, category_keywords in self.categories.items():
            score = 0
            for keyword in category_keywords:
                if keyword.lower() in searchable:
                    score += 1
            
            if score > 0:
                category_scores[category_name] = score
        
        # Return category with highest score
        if category_scores:
            best_category = max(category_scores.items(), key=lambda x: x[1])
            return best_category[0]
        
        return ""
    
    def categorize_multi(
        self,
        text: str,
        title: str = "",
        keywords: list[str] | None = None,
        min_score: int = 1,
    ) -> list[str]:
        """Categorize a document into multiple categories.
        
        Args:
            text: Document text content
            title: Document title
            keywords: Extracted keywords
            min_score: Minimum score threshold for including a category
            
        Returns:
            List of matching category names
        """
        # Combine all searchable content
        searchable = f"{title} {text}".lower()
        if keywords:
            searchable += " " + " ".join(keywords).lower()
        
        # Score each category
        matching_categories = []
        
        for category_name, category_keywords in self.categories.items():
            score = 0
            for keyword in category_keywords:
                if keyword.lower() in searchable:
                    score += 1
            
            if score >= min_score:
                matching_categories.append(category_name)
        
        return matching_categories
    
    def filter_by_category(
        self,
        documents: list[dict[str, Any]],
        categories: list[str],
    ) -> list[dict[str, Any]]:
        """Filter documents by category.
        
        Args:
            documents: List of document dictionaries with 'category' field
            categories: List of categories to include
            
        Returns:
            Filtered list of documents
        """
        if not categories:
            return documents
        
        return [
            doc for doc in documents
            if doc.get("category") in categories
        ]
