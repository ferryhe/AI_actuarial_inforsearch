"""
Query routing and KB selection for chatbot.

Analyzes user queries and selects appropriate knowledge bases.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set

from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager, KnowledgeBase
from ai_actuarial.storage import Storage
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import InvalidKBException

logger = logging.getLogger(__name__)


class QueryRouter:
    """
    Routes queries to appropriate knowledge bases.
    
    Features:
    - Automatic KB selection based on query analysis
    - Intent classification
    - Keyword-based matching (MVP approach)
    """
    
    def __init__(
        self,
        storage: Storage,
        config: Optional[ChatbotConfig] = None
    ):
        """
        Initialize query router.
        
        Args:
            storage: Storage instance for database access
            config: Chatbot configuration
        """
        self.storage = storage
        self.config = config or ChatbotConfig.from_config(storage=storage)
        self.kb_manager = KnowledgeBaseManager(storage)
        
        # Common actuarial/insurance keywords by category
        self.category_keywords = {
            'regulation': [
                'solvency', 'regulation', 'compliance', 'regulatory', 'directive',
                'ifrs', 'gaap', 'standard', 'requirement', 'capital requirement'
            ],
            'products': [
                'life insurance', 'term life', 'whole life', 'annuity', 'pension',
                'health insurance', 'disability', 'long-term care', 'variable',
                'universal life', 'endowment'
            ],
            'mathematics': [
                'formula', 'calculation', 'actuarial', 'mortality', 'interest rate',
                'discount', 'present value', 'reserve', 'premium', 'valuation',
                'stochastic', 'deterministic', 'probability'
            ],
            'risk': [
                'risk', 'underwriting', 'claims', 'loss', 'exposure', 'hedging',
                'reinsurance', 'risk management', 'market risk', 'credit risk'
            ]
        }
        
        logger.info("Initialized query router")
    
    def select_kb(
        self,
        query: str,
        available_kbs: Optional[List[KnowledgeBase]] = None,
        threshold: float = 0.3
    ) -> List[str]:
        """
        Select knowledge base(s) for a query.
        
        Uses keyword-based matching to score each KB's relevance.
        
        Args:
            query: User's question
            available_kbs: List of available KBs (default: all KBs)
            threshold: Minimum relevance score (0-1) to select a KB
        
        Returns:
            List of selected KB IDs (sorted by relevance)
        
        Raises:
            InvalidKBException: If no KBs available or selection fails
        """
        # Get available KBs
        if available_kbs is None:
            available_kbs = self.kb_manager.list_kbs()
        
        if not available_kbs:
            raise InvalidKBException("No knowledge bases available")
        
        logger.info(f"Selecting KB for query: {query[:100]}...")
        
        # Extract query features
        keywords = self._extract_keywords(query)
        entities = self._extract_entities(query)
        categories = self._classify_categories(query)
        
        logger.debug(
            f"Query features: keywords={keywords[:5]}, "
            f"entities={entities[:5]}, categories={categories}"
        )
        
        # Score each KB
        kb_scores = {}
        for kb in available_kbs:
            score = self._calculate_relevance(
                kb, keywords, entities, categories
            )
            kb_scores[kb.kb_id] = {
                'score': score,
                'name': kb.name
            }
        
        # Sort by score
        sorted_kbs = sorted(
            kb_scores.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        
        # Apply threshold
        selected_kbs = []
        for kb_id, info in sorted_kbs:
            if info['score'] >= threshold:
                selected_kbs.append(kb_id)
                logger.info(
                    f"Selected KB '{info['name']}' (id={kb_id}, score={info['score']:.2f})"
                )
        
        # If no KB meets threshold, select top KB
        if not selected_kbs and sorted_kbs:
            top_kb_id = sorted_kbs[0][0]
            top_kb_name = sorted_kbs[0][1]['name']
            top_score = sorted_kbs[0][1]['score']
            selected_kbs = [top_kb_id]
            logger.info(
                f"No KB met threshold, defaulting to top KB '{top_kb_name}' "
                f"(score={top_score:.2f})"
            )
        
        # If top 2-3 scores are close (within 0.2), select multiple
        if len(sorted_kbs) >= 2:
            top_score = sorted_kbs[0][1]['score']
            
            # Check if second KB is close
            for kb_id, info in sorted_kbs[1:4]:  # Check up to 3 more KBs
                if top_score - info['score'] <= 0.2 and kb_id not in selected_kbs:
                    selected_kbs.append(kb_id)
                    logger.info(
                        f"Added KB '{info['name']}' (score={info['score']:.2f}, "
                        f"close to top score {top_score:.2f})"
                    )
        
        if not selected_kbs:
            raise InvalidKBException("Failed to select any knowledge base")
        
        return selected_kbs

    def select_kbs(
        self,
        query: str,
        available_kbs: Optional[List[KnowledgeBase]] = None,
        threshold: float = 0.3
    ) -> List[str]:
        """Backward-compatible alias for select_kb()."""
        return self.select_kb(
            query=query,
            available_kbs=available_kbs,
            threshold=threshold,
        )
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze query intent and characteristics.
        
        Args:
            query: User's question
        
        Returns:
            Analysis dict with:
            - intent: Query intent type
            - keywords: Extracted keywords
            - entities: Identified entities
            - categories: Relevant categories
            - complexity: Query complexity (low, medium, high)
        """
        # Extract features
        keywords = self._extract_keywords(query)
        entities = self._extract_entities(query)
        categories = self._classify_categories(query)
        
        # Classify intent
        intent = self._classify_intent(query)
        
        # Assess complexity
        complexity = self._assess_complexity(query, keywords)
        
        analysis = {
            'intent': intent,
            'keywords': keywords,
            'entities': entities,
            'categories': list(categories),
            'complexity': complexity,
            'word_count': len(query.split()),
            'has_question_mark': '?' in query
        }
        
        logger.info(
            f"Query analysis: intent={intent}, complexity={complexity}, "
            f"categories={categories}"
        )
        
        return analysis
    
    def _extract_keywords(self, query: str) -> List[str]:
        """
        Extract important keywords from query.
        
        Args:
            query: User's question
        
        Returns:
            List of keywords (lowercase, cleaned)
        """
        # Convert to lowercase
        text = query.lower()
        
        # Remove punctuation except hyphens (for terms like "risk-based")
        text = re.sub(r'[^\w\s-]', ' ', text)
        
        # Split into words
        words = text.split()
        
        # Remove stopwords
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'can', 'may', 'might', 'must', 'this',
            'that', 'these', 'those', 'what', 'which', 'who', 'when', 'where',
            'why', 'how', 'it', 'its', 'they', 'them', 'their'
        }
        
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        
        # Also extract multi-word phrases (bigrams, trigrams)
        bigrams = [
            f"{words[i]} {words[i+1]}"
            for i in range(len(words)-1)
            if words[i] not in stopwords or words[i+1] not in stopwords
        ]
        
        # Check if bigrams are known terms
        for bigram in bigrams:
            # Check against category keywords
            for cat_keywords in self.category_keywords.values():
                if bigram in cat_keywords:
                    keywords.append(bigram)
                    break
        
        return keywords
    
    def _extract_entities(self, query: str) -> List[str]:
        """
        Extract named entities (regulations, products, etc.).
        
        Simple regex-based approach for MVP.
        
        Args:
            query: User's question
        
        Returns:
            List of identified entities
        """
        entities = []
        
        # Common regulation names
        regulations = [
            'solvency ii', 'solvency 2', 'ifrs 17', 'ifrs17', 'gaap',
            'us gaap', 'fas', 'ldti', 'naic', 'rbc', 'iais', 'bcbs'
        ]
        
        query_lower = query.lower()
        
        for reg in regulations:
            if reg in query_lower:
                entities.append(reg)
        
        # Extract years/dates
        years = re.findall(r'\b(19\d{2}|20\d{2})\b', query)
        entities.extend(years)
        
        # Extract capitalized terms (likely proper nouns)
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        entities.extend(capitalized[:5])  # Limit to avoid noise
        
        return entities
    
    def _classify_categories(self, query: str) -> Set[str]:
        """
        Classify query into categories based on keywords.
        
        Args:
            query: User's question
        
        Returns:
            Set of relevant categories
        """
        query_lower = query.lower()
        categories = set()
        
        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    categories.add(category)
                    break
        
        return categories
    
    def _classify_intent(self, query: str) -> str:
        """
        Classify query intent.
        
        Args:
            query: User's question
        
        Returns:
            Intent type: factual, explanatory, comparative, procedural, exploratory
        """
        query_lower = query.lower()
        
        # Comparative
        if any(word in query_lower for word in [
            'difference', 'compare', 'versus', 'vs', 'better', 'worse',
            'similar', 'different'
        ]):
            return 'comparative'
        
        # Procedural
        if any(word in query_lower for word in [
            'how to', 'how do i', 'steps', 'process', 'calculate',
            'compute', 'determine'
        ]):
            return 'procedural'
        
        # Explanatory
        if any(word in query_lower for word in [
            'how does', 'why', 'explain', 'what is', 'what are',
            'describe', 'meaning', 'definition'
        ]):
            return 'explanatory'
        
        # Factual (specific fact lookup)
        if any(word in query_lower for word in [
            'what is the', 'what are the', 'when', 'where', 'who',
            'which', 'value', 'rate', 'amount'
        ]):
            return 'factual'
        
        # Default: exploratory
        return 'exploratory'
    
    def _assess_complexity(self, query: str, keywords: List[str]) -> str:
        """
        Assess query complexity.
        
        Args:
            query: User's question
            keywords: Extracted keywords
        
        Returns:
            Complexity level: low, medium, high
        """
        word_count = len(query.split())
        keyword_count = len(keywords)
        
        # High complexity indicators
        if word_count > 30 or keyword_count > 8:
            return 'high'
        
        # Check for complex terms
        complex_terms = [
            'stochastic', 'deterministic', 'monte carlo', 'var', 'cvar',
            'copula', 'martingale', 'optimization', 'derivative'
        ]
        
        if any(term in query.lower() for term in complex_terms):
            return 'high'
        
        # Low complexity
        if word_count < 10 or keyword_count < 3:
            return 'low'
        
        # Default: medium
        return 'medium'
    
    def _calculate_relevance(
        self,
        kb: KnowledgeBase,
        keywords: List[str],
        entities: List[str],
        categories: Set[str]
    ) -> float:
        """
        Calculate KB relevance score for query.
        
        Args:
            kb: Knowledge base
            keywords: Query keywords
            entities: Query entities
            categories: Query categories
        
        Returns:
            Relevance score (0-1)
        """
        score = 0.0
        
        # Get KB metadata
        kb_categories = self.kb_manager.get_kb_categories(kb.kb_id)
        kb_name_lower = kb.name.lower()
        kb_desc_lower = kb.description.lower()
        
        # Category matching (40% weight)
        if kb_categories and categories:
            matching_categories = set(kb_categories) & categories
            category_score = len(matching_categories) / max(len(categories), 1)
            score += 0.4 * category_score
        
        # Keyword matching in KB name/description (40% weight)
        if keywords:
            keyword_matches = 0
            for keyword in keywords:
                if keyword in kb_name_lower or keyword in kb_desc_lower:
                    keyword_matches += 1
            
            keyword_score = keyword_matches / len(keywords)
            score += 0.4 * keyword_score
        
        # Entity matching (20% weight)
        if entities:
            entity_matches = 0
            for entity in entities:
                entity_lower = entity.lower()
                if entity_lower in kb_name_lower or entity_lower in kb_desc_lower:
                    entity_matches += 1
            
            entity_score = entity_matches / len(entities)
            score += 0.2 * entity_score
        
        return min(score, 1.0)  # Cap at 1.0
    
    def recommend_mode(self, query_analysis: Dict[str, Any]) -> str:
        """
        Recommend chatbot mode based on query analysis.
        
        Args:
            query_analysis: Output from analyze_query()
        
        Returns:
            Recommended mode: expert, summary, tutorial, comparison
        """
        intent = query_analysis.get('intent', 'exploratory')
        complexity = query_analysis.get('complexity', 'medium')
        
        # Comparison mode for comparative queries
        if intent == 'comparative':
            return 'comparison'
        
        # Tutorial mode for "how to" questions
        if intent == 'procedural' or intent == 'explanatory':
            # Use tutorial for simpler queries, expert for complex
            if complexity == 'low':
                return 'tutorial'
            else:
                return 'expert'
        
        # Summary mode for simple factual queries
        if intent == 'factual' and complexity == 'low':
            return 'summary'
        
        # Default: expert mode
        return 'expert'
