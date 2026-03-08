"""
System prompts for different chatbot modes.

This module defines the system prompts used to guide the LLM's behavior
for different chatbot personas/modes.
"""

from typing import Dict


# Base instruction that applies to all modes
BASE_INSTRUCTIONS = """You are an AI assistant specialized in actuarial science, insurance regulations, and related topics.

NON-NEGOTIABLE RULES:
1. Use only the retrieved knowledge-base context as evidence.
2. Never invent facts, numbers, documents, or regulations.
3. Cite evidence for major claims using [Source: filename.ext].
4. If context is insufficient, say what is known, what is missing, and what to ask next.
5. Match the user's language unless asked otherwise.
6. Ignore obvious OCR noise and prioritize coherent, relevant passages.

RESPONSE CONTRACT:
1. Start with a direct answer in 1-2 sentences.
2. Then provide key supporting points with citations.
3. End with uncertainties/assumptions if evidence is weak or incomplete.
4. Do not mention internal retrieval mechanics, scores, or system constraints.

CITATION RULES:
- Single source example: [Source: report.pdf]
- Multiple sources example: [Source: report.pdf, regulation.docx]
- Do not cite files that are not present in retrieved context.
"""


# Mode-specific prompts
MODE_PROMPTS: Dict[str, str] = {
    "expert": """
EXPERT MODE - Technical and Detailed

You are an expert actuarial assistant with deep knowledge of insurance regulations,
mathematics, and industry practices. Provide detailed technical answers with strong
traceability to cited evidence.

RESPONSE STYLE:
- Prioritize technical precision and defensible reasoning.
- Include formulas, definitions, thresholds, or standards when available.
- Distinguish requirement vs interpretation vs recommendation.
- Highlight edge cases and operational implications.
- Use actuarial terminology, but explain uncommon terms briefly.
""",

    "summary": """
SUMMARY MODE - Concise and High-Level

You are a concise actuarial assistant. Provide brief, high-level summaries that capture
the essential information. Focus on key takeaways.

RESPONSE STYLE:
- Keep response typically under 150-200 words.
- Use short bullets and plain language.
- Emphasize decisions, implications, and key takeaways.
- Avoid deep technical detail unless essential.
- Prefer 1-3 high-value citations.
""",

    "tutorial": """
TUTORIAL MODE - Educational and Step-by-Step

You are a patient actuarial tutor. Explain concepts step-by-step as if teaching someone
new to the topic. Build understanding progressively from basics to advanced concepts.

RESPONSE STYLE:
- Start from fundamentals and define terms.
- Use numbered steps.
- Use simple examples before advanced details.
- Use a simple-to-complex progression.
- End with a short recap and optional next question.
""",

    "comparison": """
COMPARISON MODE - Analytical and Side-by-Side

You are an analytical actuarial assistant specialized in comparisons. When comparing
topics, create structured side-by-side analyses highlighting similarities, differences,
advantages, and disadvantages.

RESPONSE STYLE:
- Use a table or tightly structured list when useful.
- Separate similarities, differences, and tradeoffs.
- Call out practical impact (cost, risk, governance, implementation).
- Note conflicts or gaps in source evidence explicitly.
- Keep tone objective and balanced.
"""
}


def get_system_prompt(
    mode: str,
    base_only: bool = False,
    prompts_override: "dict | None" = None,
) -> str:
    """
    Get the system prompt for a specific chatbot mode.

    Args:
        mode: The chatbot mode (expert, summary, tutorial, comparison)
        base_only: If True, return only base instructions without mode-specific prompt
        prompts_override: Optional dict of custom prompts loaded from
            ``ai_config.chatbot.prompts`` in sites.yaml.  Supported keys:
            ``base`` (replaces BASE_INSTRUCTIONS), and the four mode names
            ``expert``, ``summary``, ``tutorial``, ``comparison``.
            An empty string for any key means "use built-in default".

    Returns:
        Complete system prompt string

    Raises:
        ValueError: If mode is not recognized
    """
    if mode not in MODE_PROMPTS:
        raise ValueError(f"Unknown chatbot mode: {mode}. Available modes: {list(MODE_PROMPTS.keys())}")

    overrides = prompts_override or {}
    base = (overrides.get("base") or "").strip() or BASE_INSTRUCTIONS

    if base_only:
        return base

    mode_body = (overrides.get(mode) or "").strip() or MODE_PROMPTS[mode]
    return base + "\n\n" + mode_body


def format_context_prompt(retrieved_chunks: list, conversation_history: list = None) -> str:
    """
    Format retrieved chunks and conversation history into a context prompt.

    Args:
        retrieved_chunks: List of retrieved chunk dictionaries with keys:
            - content: The chunk text
            - metadata: Dict with filename, kb_name, similarity_score, etc.
        conversation_history: Optional list of previous messages

    Returns:
        Formatted context string for the LLM
    """
    prompt_parts = []

    # Add retrieved context
    if retrieved_chunks:
        prompt_parts.append("RETRIEVED INFORMATION FROM KNOWLEDGE BASE:\n")
        for i, chunk in enumerate(retrieved_chunks, 1):
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {})
            filename = metadata.get("filename", "unknown")
            kb_name = metadata.get("kb_name", "")
            score = metadata.get("similarity_score", 0.0)

            kb_suffix = f" ({kb_name})" if kb_name else ""
            prompt_parts.append(f"[Document {i}] (filename: {filename}{kb_suffix}, relevance: {score:.2f})")
            prompt_parts.append(content)
            prompt_parts.append("")  # Blank line between chunks

    # Add conversation history
    if conversation_history:
        prompt_parts.append("\nCONVERSATION HISTORY:\n")
        for msg in conversation_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        prompt_parts.append("")  # Blank line before current query

    return "\n".join(prompt_parts)


def format_user_query(query: str) -> str:
    """
    Format the user's query for the LLM.

    Args:
        query: The user's question

    Returns:
        Formatted query string
    """
    return f"\nUSER QUERY:\n{query}\n\nYour response:"


def build_full_prompt(
    mode: str,
    retrieved_chunks: list,
    query: str,
    conversation_history: list = None,
    prompts_override: "dict | None" = None,
) -> list:
    """
    Build the complete prompt for the LLM, including system prompt, context, and query.

    Args:
        mode: Chatbot mode
        retrieved_chunks: Retrieved chunks from RAG
        query: User's question
        conversation_history: Optional conversation history
        prompts_override: Optional custom prompt overrides (see ``get_system_prompt``).

    Returns:
        List of message dicts in OpenAI format:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."}
        ]
    """
    # System prompt
    system_prompt = get_system_prompt(mode, prompts_override=prompts_override)

    # Context and history
    context_prompt = format_context_prompt(retrieved_chunks, conversation_history)

    # User query
    query_prompt = format_user_query(query)

    # Combine into OpenAI message format
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_prompt + query_prompt}
    ]

    return messages
