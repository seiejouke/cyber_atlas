"""Small, inert study-text markup: headings, lists, emphasis and concept links."""
from dataclasses import dataclass
import re
from urllib.parse import quote, unquote


@dataclass(frozen=True)
class StudySpan:
    text: str
    tags: tuple[str, ...] = ()
    concept_id: str | None = None


INLINE = re.compile(r'\[([^\]\n]{1,120})\]\(concept:([^)\n]{1,500})\)|\*\*([^*\n]+)\*\*|(?<!\*)\*([^*\n]+)\*(?!\*)|`([^`\n]+)`')


def concept_link(identity, name):
    return f"[{name.replace(']', '')}](concept:{quote(identity, safe='')})"


def study_spans(text):
    spans = []
    for line in text.splitlines(keepends=True):
        tags = ()
        heading = re.match(r'^(#{1,3})\s+', line)
        if heading:
            tags = (f'h{len(heading[1])}',)
            line = line[heading.end():]
        elif line.startswith(('- ', '* ')):
            line = '\u2022 ' + line[2:]
        start = 0
        for match in INLINE.finditer(line):
            if match.start() > start:
                spans.append(StudySpan(line[start:match.start()], tags))
            if match[1] is not None:
                spans.append(StudySpan(match[1], tags + ('link',), unquote(match[2])))
            else:
                index = next(i for i in (3, 4, 5) if match[i] is not None)
                spans.append(StudySpan(match[index], tags + ({3: 'bold', 4: 'italic', 5: 'code'}[index],)))
            start = match.end()
        if start < len(line):
            spans.append(StudySpan(line[start:], tags))
    return tuple(spans)
