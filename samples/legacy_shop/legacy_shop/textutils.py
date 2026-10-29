# -*- coding: utf-8 -*-
"""Text helpers for the shop."""
import re
import string


def slugify(title):
    """Turn a product title into a URL slug (returns a byte string)."""
    if isinstance(title, str):
        title = title.decode('utf-8')
    title = title.lower()
    out = []
    for ch in title:
        if ch.isalnum():
            out.append(ch)
        elif ch in u' -_':
            out.append(u'-')
    slug = re.sub(u'-+', u'-', u''.join(out)).strip(u'-')
    return slug.encode('ascii', 'ignore')


def word_frequencies(text):
    counts = {}
    for word in text.lower().split():
        word = word.strip(string.punctuation)
        if not word:
            continue
        if counts.has_key(word):
            counts[word] += 1
        else:
            counts[word] = 1
    return counts


def top_words(text, n=3):
    """Most common words, ties broken alphabetically."""
    counts = word_frequencies(text)
    pairs = counts.items()
    pairs.sort(lambda a, b: cmp(b[1], a[1]) or cmp(a[0], b[0]))
    return pairs[:n]


def wrap_text(text, width=40):
    lines = []
    line = ''
    for word in text.split():
        if len(line) + len(word) + 1 > width and line:
            lines.append(line)
            line = word
        else:
            line = (line + ' ' + word).strip()
    if line:
        lines.append(line)
    return lines


def center_title(title, width=40):
    pad = (width - len(title)) / 2
    return ' ' * pad + title
