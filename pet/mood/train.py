"""Trains the mood classifier from scratch for one or all supported
languages, on our own hand-written datasets (pet/mood/datasets/<lang>.py)
— random weight initialization, no pretrained model or embeddings
involved. Run after editing a dataset to (re)produce
pet/mood/model/<lang>/mood_model.pt + mood_vocab.json:

    python -m pet.mood.train             # trains every supported language
    python -m pet.mood.train --lang en   # trains just one
"""

import argparse
import random

import torch
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset

import config
from pet.mood.datasets import get_dataset
from pet.mood.model import MAX_LEN, MoodNet
from pet.mood.vocab import build_vocab, encode, save_vocab


class _MoodDataset(Dataset):
    def __init__(self, examples, vocab, label_to_idx):
        self.examples = examples
        self.vocab = vocab
        self.label_to_idx = label_to_idx

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        text, label = self.examples[idx]
        ids = encode(text, self.vocab, MAX_LEN)
        return torch.tensor(ids, dtype=torch.long), self.label_to_idx[label]


def train(lang: str = config.DEFAULT_LANGUAGE, epochs: int = 150, lr: float = 1e-2, seed: int = 0) -> float:
    dataset_module = get_dataset(lang)
    examples_source, labels = dataset_module.EXAMPLES, dataset_module.LABELS

    random.seed(seed)
    torch.manual_seed(seed)

    vocab = build_vocab([text for text, _ in examples_source])
    label_to_idx = {label: i for i, label in enumerate(labels)}

    examples = list(examples_source)
    random.shuffle(examples)
    dataset = _MoodDataset(examples, vocab, label_to_idx)
    loader = DataLoader(dataset, batch_size=16, shuffle=True)

    model = MoodNet(vocab_size=len(vocab), num_classes=len(labels))
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    model.train()
    accuracy = 0.0
    for epoch in range(epochs):
        total_loss, correct = 0.0, 0
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(batch_y)
            correct += (logits.argmax(dim=1) == batch_y).sum().item()

        accuracy = correct / len(dataset)
        if (epoch + 1) % 25 == 0 or epoch == epochs - 1:
            print(f"[{lang}] epoch {epoch + 1}/{epochs}  loss={total_loss / len(dataset):.4f}  train_acc={accuracy:.1%}")

    model_dir = config.MOOD_MODEL_DIR / lang
    model_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_dir / "mood_model.pt")
    save_vocab(vocab, model_dir / "mood_vocab.json")
    print(f"[{lang}] salvato in {model_dir} ({len(examples_source)} frasi, {len(labels)} categorie)")
    return accuracy


def main():
    parser = argparse.ArgumentParser(description="Allena il classificatore di umore.")
    parser.add_argument("--lang", choices=config.SUPPORTED_LANGUAGES, default=None,
                         help="Lingua da allenare; se omesso, le allena tutte.")
    args = parser.parse_args()

    languages = [args.lang] if args.lang else config.SUPPORTED_LANGUAGES
    for lang in languages:
        train(lang)


if __name__ == "__main__":
    main()
