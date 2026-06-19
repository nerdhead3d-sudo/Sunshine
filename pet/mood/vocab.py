"""Our own tiny tokenizer + vocabulary for the mood classifier — plain
whitespace/punctuation splitting and a word->index table built directly
from the training set, with no pretrained tokenizer or embeddings
involved. The accented-letter range covers Italian/French/Spanish/
Portuguese accents; ß is added explicitly for German."""

import json
import re
from pathlib import Path

PAD = "<pad>"
UNK = "<unk>"

_TOKEN_RE = re.compile(r"[a-zà-ÿß']+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def build_vocab(texts: list[str]) -> dict[str, int]:
    vocab = {PAD: 0, UNK: 1}
    for text in texts:
        for token in tokenize(text):
            if token not in vocab:
                vocab[token] = len(vocab)
    return vocab


def encode(text: str, vocab: dict[str, int], max_len: int) -> list[int]:
    ids = [vocab.get(token, vocab[UNK]) for token in tokenize(text)][:max_len]
    ids += [vocab[PAD]] * (max_len - len(ids))
    return ids


def save_vocab(vocab: dict[str, int], path: Path):
    path.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")


def load_vocab(path: Path) -> dict[str, int]:
    return json.loads(path.read_text(encoding="utf-8"))
