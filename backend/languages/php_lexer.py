"""Small PHP-aware lexical inventory, not a PHP parser or syntax verifier.

Only PHP tags are examined. Comments, literals, heredoc/nowdoc and backticks
are opaque; they never become declarations/calls. No interpreter is invoked.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int


OPEN = re.compile(r"<\?(?:php(?=\s|$)|=)", re.IGNORECASE)
NAME = re.compile(r"[a-zA-Z_\x80-\uffff][a-zA-Z_0-9\x80-\uffff]*")
HEREDOC = re.compile(r"<<<[ \t]*(['\"]?)([a-zA-Z_][a-zA-Z_0-9]*)\1[^\S\r\n]*\r?\n")
OPERATORS = ("?->", "===", "!==", "...", "->", "::", "=>", "==", "!=", "<=", ">=", "??", "&&", "||")


def lex(text):
    tokens, errors = [], []
    position, line, inside = 0, 1, False
    while position < len(text):
        if not inside:
            opening = OPEN.search(text, position)
            if not opening:
                break
            line += text[position:opening.end()].count("\n")
            position, inside = opening.end(), True
            continue
        start, start_line = position, line
        char = text[position]
        if text.startswith("?>", position):
            position += 2; inside = False; continue
        if char.isspace():
            line += char == "\n"; position += 1; continue
        if text.startswith("//", position) or (char == "#" and not text.startswith("#[", position)):
            end = text.find("\n", position)
            close = text.find("?>", position)
            position = min(x for x in (end, close, len(text)) if x >= 0)
            continue
        if text.startswith("/*", position):
            end = text.find("*/", position + 2)
            if end < 0:
                errors.append({"code": "unterminated_comment", "line": line}); break
            position = end + 2; line += text[start:position].count("\n"); continue
        heredoc = HEREDOC.match(text, position)
        if heredoc:
            ending = re.search(r"(?m)^[ \t]*" + re.escape(heredoc[2]) + r"(?=[;,\)\r\n]|$)", text[heredoc.end():])
            if not ending:
                errors.append({"code": "unterminated_heredoc", "line": line}); break
            position = heredoc.end() + ending.end()
            line += text[start:position].count("\n")
            tokens.append(Token("opaque", "", start_line)); continue
        if char in "'\"`":
            position += 1
            while position < len(text):
                if text[position] == "\\":
                    position += 2; continue
                if text[position] == char:
                    break
                position += 1
            if position >= len(text):
                errors.append({"code": "unterminated_literal", "line": line}); break
            literal = text[start + 1:position]
            position += 1; line += text[start:position].count("\n")
            # Keep simple literals solely for static include candidates. Never
            # decode/interpolate PHP strings on the host or export all literals.
            kind = "string" if char != "`" and "\\" not in literal and not (char == '"' and "$" in literal) else "opaque"
            tokens.append(Token(kind, literal if kind == "string" else "", start_line)); continue
        match = NAME.match(text, position + 1 if char == "$" else position)
        if match:
            position = match.end()
            tokens.append(Token("variable" if char == "$" else "name", ("$" if char == "$" else "") + match[0], line)); continue
        operator = next((op for op in OPERATORS if text.startswith(op, position)), char)
        tokens.append(Token("symbol", operator, line)); position += len(operator)
    return tokens, errors
