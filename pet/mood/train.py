"""Trains the mood classifier from scratch on our own hand-written dataset
(pet/mood/dataset.py) — random weight initialization, no pretrained model
or embeddings involved. Run after editing the dataset to (re)produce
pet/mood/model/mood_model.pt + mood_vocab.json:

    python -m pet.mood.train
"""

import random

import torch
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset

import config
from pet.mood.dataset import EXAMPLES, LABELS
from pet.mood.model import MoodNet
from pet.mood.vocab import build_vocab, encode, save_vocab
from pet.mood.model import MAX_LEN


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


def train(epochs: int = 150, lr: float = 1e-2, seed: int = 0) -> float:
    random.seed(seed)
    torch.manual_seed(seed)

    vocab = build_vocab([text for text, _ in EXAMPLES])
    label_to_idx = {label: i for i, label in enumerate(LABELS)}

    examples = list(EXAMPLES)
    random.shuffle(examples)
    dataset = _MoodDataset(examples, vocab, label_to_idx)
    loader = DataLoader(dataset, batch_size=16, shuffle=True)

    model = MoodNet(vocab_size=len(vocab), num_classes=len(LABELS))
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
            print(f"epoch {epoch + 1}/{epochs}  loss={total_loss / len(dataset):.4f}  train_acc={accuracy:.1%}")

    config.MOOD_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), config.MOOD_MODEL_DIR / "mood_model.pt")
    save_vocab(vocab, config.MOOD_MODEL_DIR / "mood_vocab.json")
    print(f"Salvato in {config.MOOD_MODEL_DIR}")
    return accuracy


if __name__ == "__main__":
    train()
