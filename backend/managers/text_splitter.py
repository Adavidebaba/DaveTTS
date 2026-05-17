"""
Divisione intelligente del testo in chunk rispettando i limiti API.
Spezza su fine paragrafo, poi su fine frase, mai a metà parola.
"""

import re


class TextSplitter:
    """Divide un testo lungo in chunk di dimensione sicura per l'API TTS."""

    def __init__(self, max_chunk_size: int = 10_000):
        self.max_chunk_size = max_chunk_size

    def split(self, text: str) -> list[str]:
        """
        Divide il testo in chunk.
        Priorità di taglio: paragrafo > frase > spazio.
        """
        text = self._normalize(text)

        if len(text) <= self.max_chunk_size:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= self.max_chunk_size:
                chunks.append(remaining.strip())
                break

            cut_point = self._find_best_cut(remaining)
            chunk = remaining[:cut_point].strip()

            if chunk:
                chunks.append(chunk)

            remaining = remaining[cut_point:].strip()

        return [c for c in chunks if c]

    def _normalize(self, text: str) -> str:
        """Normalizza spazi bianchi e caratteri speciali."""
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _find_best_cut(self, text: str) -> int:
        """Trova il miglior punto di taglio entro il limite."""
        limit = self.max_chunk_size

        # Priorità 1: Taglio su doppio a capo (fine paragrafo)
        cut = self._find_last_occurrence(text, "\n\n", limit)
        if cut > 0:
            return cut + 2  # Includi il separatore

        # Priorità 2: Taglio su singolo a capo
        cut = self._find_last_occurrence(text, "\n", limit)
        if cut > 0:
            return cut + 1

        # Priorità 3: Taglio su fine frase (. ! ?)
        cut = self._find_last_sentence_end(text, limit)
        if cut > 0:
            return cut

        # Priorità 4: Taglio su spazio (mai a metà parola)
        cut = self._find_last_occurrence(text, " ", limit)
        if cut > 0:
            return cut + 1

        # Fallback: taglio duro al limite
        return limit

    def _find_last_occurrence(self, text: str, separator: str, limit: int) -> int:
        """Trova l'ultima occorrenza del separatore entro il limite."""
        search_area = text[:limit]
        return search_area.rfind(separator)

    def _find_last_sentence_end(self, text: str, limit: int) -> int:
        """Trova la fine dell'ultima frase completa entro il limite."""
        search_area = text[:limit]
        # Cerca l'ultimo punto, punto esclamativo o interrogativo
        # seguito da spazio o fine testo
        match = None
        for m in re.finditer(r'[.!?][\s]', search_area):
            match = m

        if match:
            return match.end()

        # Controlla se il testo finisce con un punto
        last_punct = max(
            search_area.rfind(". "),
            search_area.rfind("! "),
            search_area.rfind("? "),
        )
        if last_punct > 0:
            return last_punct + 2

        return -1

    def estimate_chunks(self, text: str) -> int:
        """Stima il numero di chunk senza effettuare lo split."""
        text = self._normalize(text)
        if not text:
            return 0
        return max(1, -(-len(text) // self.max_chunk_size))
