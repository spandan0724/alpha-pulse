"""Article summarization for AlphaPulse.

Uses BART transformer for free summarization with proper chunking.
Handles large articles by breaking into 500-word chunks.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_summarizer = None


def _get_summarizer():
    """Lazy-load BART summarizer (one-time ~1GB download)."""
    global _summarizer
    if _summarizer is None:
        try:
            from transformers import pipeline

            logger.info("Loading BART summarization model...")
            _summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
            logger.info("Summarizer ready")
        except ImportError:
            logger.error(
                "transformers not installed. Install with: pip install transformers torch sentencepiece"
            )
            return None
    return _summarizer


def summarize_huge_text(text: str, max_chunk_words: int = 500) -> Optional[str]:
    """Summarize large text by chunking and combining intermediate summaries.
    
    Inspired by NewsAPI chunking pattern:
    1. Split text into 500-word chunks
    2. Summarize each chunk individually
    3. Combine intermediate summaries
    4. If combined summary is still long, final pass
    
    Args:
        text: Article text to summarize
        max_chunk_words: Words per chunk (default 500)
        
    Returns:
        Final summary or None if summarizer unavailable
    """
    if not text or len(text) < 30:
        return text if text else None
    
    words = text.split()
    if len(words) < 20:  # Lower threshold for short descriptions
        return text  # Too short to summarize
    
    summarizer = _get_summarizer()
    if not summarizer:
        logger.warning("Summarizer unavailable, returning truncation")
        return text[:300]
    
    # Split into chunks
    chunks = []
    for i in range(0, len(words), max_chunk_words):
        chunk = " ".join(words[i : i + max_chunk_words])
        chunks.append(chunk)
    
    intermediate_summaries = []
    logger.debug("Processing article in %d chunk(s)", len(chunks))
    
    try:
        # Summarize each chunk individually
        for count, chunk in enumerate(chunks):
            chunk_len = len(chunk.split())
            # Dynamic min/max based on chunk size - much smaller for short content
            max_len = max(20, min(130, int(chunk_len * 0.5)))
            min_len = max(10, min(30, int(chunk_len * 0.2)))
            
            logger.debug("Chunk %d: %d words → summary %d-%d words", count, chunk_len, min_len, max_len)
            
            summary = summarizer(chunk, max_length=max_len, min_length=min_len, do_sample=False)
            intermediate_summaries.append(summary[0]["summary_text"])
        
        # Combine all intermediate summaries
        combined = " ".join(intermediate_summaries)
        combined_len = len(combined.split())
        logger.debug("Combined intermediate summaries: %d words", combined_len)
        
        # If combined is still long, final summary pass
        if combined_len > 100:
            logger.debug("Running final summary pass on %d words", combined_len)
            final = summarizer(combined, max_length=100, min_length=30, do_sample=False)
            return final[0]["summary_text"]
        
        return combined
        
    except Exception as e:
        logger.error("Summarization failed: %s", e, exc_info=True)
        return text[:300]


def summarize_article(content: str) -> Optional[str]:
    """Summarize article using chunking strategy.
    
    Args:
        content: Article text to summarize
        
    Returns:
        Summarized text or truncated fallback
    """
    if not content:
        return None
    
    return summarize_huge_text(content)
