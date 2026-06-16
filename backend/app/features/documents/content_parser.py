from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal


BlockType = Literal["heading", "paragraph", "bullet", "numbered", "table", "code", "quote", "rule"]


@dataclass(frozen=True)
class InlineSpan:
    text: str
    bold: bool = False
    code: bool = False


@dataclass(frozen=True)
class DocumentBlock:
    type: BlockType
    text: str = ""
    spans: list[InlineSpan] = field(default_factory=list)
    level: int = 0
    rows: list[list[str]] = field(default_factory=list)
    language: str = ""


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    blocks: list[DocumentBlock]

    @property
    def tables(self) -> list[DocumentBlock]:
        return [block for block in self.blocks if block.type == "table"]

    def plain_lines(self) -> list[str]:
        lines: list[str] = []
        for block in self.blocks:
            if block.type == "table":
                for row in block.rows:
                    lines.append(" | ".join(row))
            elif block.text:
                lines.append(block.text)
        return lines


def parse_document(title: str, content: str) -> ParsedDocument:
    safe_title = re.sub(r"\s+", " ", title).strip() or "Project_R 生成文件"
    lines = _clean_document_content(content).splitlines()
    blocks: list[DocumentBlock] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            index += 1
            continue
        if _is_markdown_table_row(line):
            rows: list[list[str]] = []
            while index < len(lines):
                table_line = lines[index].strip()
                if _is_markdown_table_separator(table_line):
                    index += 1
                    continue
                if not _is_markdown_table_row(table_line):
                    break
                rows.append(_split_table_row(table_line))
                index += 1
            if rows:
                blocks.append(DocumentBlock(type="table", rows=rows))
            continue
        if re.match(r"^[-*_]{3,}$", line):
            blocks.append(DocumentBlock(type="rule"))
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            text, spans = parse_inline(heading.group(2))
            blocks.append(DocumentBlock(type="heading", text=text, spans=spans, level=len(heading.group(1))))
            index += 1
            continue
        quote = re.match(r"^>\s+(.+)$", line)
        if quote:
            text, spans = parse_inline(quote.group(1))
            blocks.append(DocumentBlock(type="quote", text=text, spans=spans))
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            text, spans = parse_inline(bullet.group(1))
            blocks.append(DocumentBlock(type="bullet", text=text, spans=spans))
            index += 1
            continue
        numbered = re.match(r"^\d+[.)、]\s+(.+)$", line)
        if numbered:
            text, spans = parse_inline(numbered.group(1))
            blocks.append(DocumentBlock(type="numbered", text=text, spans=spans))
            index += 1
            continue
        text, spans = parse_inline(line)
        blocks.append(DocumentBlock(type="paragraph", text=text, spans=spans))
        index += 1
    if not blocks:
        blocks.append(DocumentBlock(type="paragraph", text=safe_title, spans=[InlineSpan(safe_title)]))
    return ParsedDocument(title=safe_title, blocks=blocks)


def parse_inline(text: str) -> tuple[str, list[InlineSpan]]:
    normalized = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text.strip())
    spans: list[InlineSpan] = []
    position = 0
    pattern = re.compile(r"(\*\*([^*]+)\*\*|`([^`]+)`)")
    for match in pattern.finditer(normalized):
        if match.start() > position:
            spans.append(InlineSpan(normalized[position:match.start()]))
        if match.group(2) is not None:
            spans.append(InlineSpan(match.group(2), bold=True))
        elif match.group(3) is not None:
            spans.append(InlineSpan(match.group(3), code=True))
        position = match.end()
    if position < len(normalized):
        spans.append(InlineSpan(normalized[position:]))
    plain = "".join(span.text for span in spans)
    return plain, [span for span in spans if span.text]


def clean_plain_text(content: str) -> str:
    document = parse_document("", content)
    lines: list[str] = []
    for block in document.blocks:
        if block.type == "heading":
            lines.append(block.text)
        elif block.type in {"bullet", "numbered"}:
            lines.append(f"- {block.text}")
        elif block.type == "table":
            lines.extend(" | ".join(row) for row in block.rows)
        elif block.text:
            lines.append(block.text)
    return "\n".join(lines).strip() + "\n"


def clean_markdown(title: str, content: str) -> str:
    text = _clean_document_content(content)
    if not re.match(r"^#\s+", text):
        safe_title = re.sub(r"\s+", " ", title).strip() or "Project_R 生成文件"
        text = f"# {safe_title}\n\n{text}"
    return text.strip() + "\n"


def _clean_document_content(content: str) -> str:
    text = content.strip()
    fenced = re.findall(r"```(?:\w+)?\s*\n(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = max(fenced, key=len).strip()
    text = re.sub(r"^\s*[-*]\s*\[\[[^\]]+\]\]\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#+\s*本次使用的来源文件[:：]?\s*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*?本次回答使用的来源文件[:：]\*\*?.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_markdown_table_separator(line: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$", line.strip()))


def _is_markdown_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and stripped.count("|") >= 2 and not _is_markdown_table_separator(stripped)


def _split_table_row(line: str) -> list[str]:
    return [parse_inline(cell.strip())[0] for cell in line.strip().strip("|").split("|")]
