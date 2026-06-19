"""The mood classifier's network architecture — a small embedding + mean
pooling + MLP, trained entirely from scratch (random init, no pretrained
weights of any kind) on pet/mood/datasets/<lang>.py.

10 learnable tensors in total: embedding.weight, 3x(hidden.weight+bias),
out.weight+out.bias, and a learned scalar `temperature` that rescales the
final logits — added as an experiment to see whether more depth helps a
network this small trained on ~270 sentences (spoiler: not much, the
bottleneck is data, not depth — see README)."""

import torch
from torch import nn

EMBED_DIM = 32
HIDDEN_DIM = 32
MAX_LEN = 16


class MoodNet(nn.Module):
    def __init__(self, vocab_size: int, num_classes: int, embed_dim: int = EMBED_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)  # tensor 1
        self.hidden1 = nn.Linear(embed_dim, hidden_dim)                      # tensors 2-3
        self.hidden2 = nn.Linear(hidden_dim, hidden_dim)                     # tensors 4-5
        self.hidden3 = nn.Linear(hidden_dim, hidden_dim)                     # tensors 6-7
        self.out = nn.Linear(hidden_dim, num_classes)                       # tensors 8-9
        self.temperature = nn.Parameter(torch.ones(1))                      # tensor 10
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len) token ids, 0 = padding
        emb = self.embedding(x)
        mask = (x != 0).unsqueeze(-1).float()
        summed = (emb * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1.0)
        pooled = summed / counts  # mean pooling, ignoring padding positions

        h = self.dropout(self.relu(self.hidden1(pooled)))
        h = self.dropout(self.relu(self.hidden2(h)))
        h = self.dropout(self.relu(self.hidden3(h)))
        return self.out(h) * self.temperature
