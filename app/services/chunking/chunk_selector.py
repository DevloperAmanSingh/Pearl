from __future__ import annotations

from typing import Iterable

from app.services.agents.base import AgentContext
from app.services.chunking.base import CodeChunk
from app.services.chunking.ast_chunker import ASTChunker
from app.services.chunking.patch_chunker import PatchChunker


class ChunkSelector:
    def __init__(self, ast_chunker: ASTChunker, patch_chunker: PatchChunker) -> None:
        self._ast_chunker = ast_chunker
        self._patch_chunker = patch_chunker

    def generate_chunks(self, context: AgentContext) -> Iterable[CodeChunk]:
        if context.language and self._ast_chunker.supports(context.language):
            ast_chunks = list(self._ast_chunker.generate_chunks(context))
            if ast_chunks:
                return ast_chunks
        return list(self._patch_chunker.generate_chunks(context))
