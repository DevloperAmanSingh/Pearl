from __future__ import annotations

from typing import Dict, Iterable, List, Set

from tree_sitter import Parser
from tree_sitter_languages import get_language

from app.services.agents.base import AgentContext
from app.services.chunking.base import CodeChunk

SUPPORTED_LANGUAGES = {
    "python": {
        "language": "python",
        "node_types": {
            "function_definition",
            "class_definition",
            "async_function_definition",
        },
    },
    "typescript": {
        "language": "typescript",
        "node_types": {
            "function_declaration",
            "method_definition",
            "class_declaration",
            "arrow_function",
        },
    },
    "tsx": {
        "language": "tsx",
        "node_types": {
            "function_declaration",
            "method_definition",
            "class_declaration",
            "arrow_function",
        },
    },
    "javascript": {
        "language": "javascript",
        "node_types": {
            "function_declaration",
            "method_definition",
            "class_declaration",
            "arrow_function",
        },
    },
    "jsx": {
        "language": "jsx",
        "node_types": {
            "function_declaration",
            "method_definition",
            "class_declaration",
            "arrow_function",
        },
    },
}


class ASTChunker:
    def __init__(self) -> None:
        self._parsers: Dict[str, Parser] = {}

    def supports(self, language: str | None) -> bool:
        return language in SUPPORTED_LANGUAGES

    def _get_parser(self, language: str) -> Parser:
        if language not in self._parsers:
            parser = Parser()
            parser.set_language(get_language(SUPPORTED_LANGUAGES[language]["language"]))
            self._parsers[language] = parser
        return self._parsers[language]

    def generate_chunks(self, context: AgentContext) -> Iterable[CodeChunk]:
        language = context.language
        source_code = context.source_code or ""
        if not language or not self.supports(language) or not source_code:
            return []

        parser = self._get_parser(language)
        tree = parser.parse(source_code.encode("utf-8"))
        node_types = SUPPORTED_LANGUAGES[language]["node_types"]
        changed_lines: Set[int] = set(context.changed_lines or [])

        chunks: List[CodeChunk] = []
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in node_types and self._node_intersects(node, changed_lines):
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                chunk_content = source_code[node.start_byte : node.end_byte]
                chunks.append(
                    CodeChunk(
                        file_path=context.file_path or "",
                        content=chunk_content,
                        diff_hunk=context.patch,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={
                            "language": language,
                            "chunk_type": node.type,
                        },
                    )
                )
                continue
            stack.extend(node.children)

        if not chunks and changed_lines:
            chunks.extend(self._fallback_chunks(context, source_code, changed_lines))

        return chunks

    @staticmethod
    def _node_intersects(node, changed_lines: Set[int]) -> bool:
        if not changed_lines:
            return False
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        for line in changed_lines:
            if start_line <= line <= end_line:
                return True
        return False

    @staticmethod
    def _fallback_chunks(context: AgentContext, source_code: str, changed_lines: Set[int]) -> List[CodeChunk]:
        lines = source_code.splitlines()
        if not lines:
            return []
        start_line = max(min(changed_lines) - 5, 1)
        end_line = min(max(changed_lines) + 5, len(lines))
        snippet = "\n".join(lines[start_line - 1 : end_line])
        return [
            CodeChunk(
                file_path=context.file_path or "",
                content=snippet,
                diff_hunk=context.patch,
                start_line=start_line,
                end_line=end_line,
                metadata={
                    "language": context.language,
                    "chunk_type": "fallback_window",
                },
            )
        ]
