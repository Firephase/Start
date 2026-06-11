"""
Speaker verification losses for training speaker encoders.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Literal, Optional


class GeneralizedEndToEndLoss(nn.Module):
    """
    Generalized End-to-End (GE2E) loss for speaker encoder training.

    Supports both softmax and contrast variants described in:
    "Generalized End-to-End Loss for Speaker Verification"
    (Wan et al., ICASSP 2018).

    The loss is computed over a batch organized as N speakers * M utterances.
    Embeddings are L2-normalized before computing cosine similarities.

    Args:
        variant: "softmax" (default) or "contrast".
        init_w: Initial value for the learnable scaling parameter w.
        init_b: Initial value for the learnable bias b.
        eps: Numerical stability constant for L2 normalization.
    """

    def __init__(
        self,
        variant: Literal["softmax", "contrast"] = "softmax",
        init_w: float = 10.0,
        init_b: float = -5.0,
        eps: float = 1e-8,
    ) -> None:
        super().__init__()
        if variant not in ("softmax", "contrast"):
            raise ValueError(f"variant must be 'softmax' or 'contrast', got '{variant}'")
        self.variant = variant
        self.eps = eps

        # Learnable scaling and bias (constrained: w > 0)
        self.w = nn.Parameter(torch.tensor(init_w))
        self.b = nn.Parameter(torch.tensor(init_b))

    @staticmethod
    def _l2_normalize(x: torch.Tensor, eps: float = 1e-8) -> torch.Tensor:
        return x / (x.norm(dim=-1, keepdim=True) + eps)

    def _centroid(
        self,
        embeddings: torch.Tensor,
        exclude_idx: Optional[int] = None,
    ) -> torch.Tensor:
        """
        Compute per-speaker centroids.

        Args:
            embeddings: (N, M, D) speaker embeddings.
            exclude_idx: If given, exclude utterance at this index within each speaker
                         from centroid computation (used in GE2E formulation).

        Returns:
            Centroids: (N, D)
        """
        N, M, D = embeddings.shape
        if exclude_idx is None:
            return embeddings.mean(dim=1)

        # Sum all then subtract excluded utterance
        total = embeddings.sum(dim=1)  # (N, D)
        total = total - embeddings[:, exclude_idx, :]  # (N, D)
        return total / (M - 1)

    def forward(
        self,
        embeddings: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
        """
        Compute GE2E loss.

        Args:
            embeddings: Speaker embeddings of shape (N*M, D) where N is the number
                        of speakers and M is the number of utterances per speaker.
                        Utterances are assumed to be ordered: all M for speaker 0,
                        then all M for speaker 1, etc.
            labels: Integer speaker IDs of shape (N*M,). Used to infer N and M.

        Returns:
            Scalar GE2E loss.
        """
        # Determine N and M from labels
        unique_labels, counts = torch.unique(labels, return_counts=True)
        N = unique_labels.size(0)
        M = counts[0].item()

        if not torch.all(counts == M):
            raise ValueError(
                "GE2E loss requires equal utterances per speaker. "
                f"Got counts: {counts.tolist()}"
            )

        D = embeddings.size(-1)

        # Re-order embeddings by label so shape is (N, M, D)
        sorted_idx = torch.argsort(labels)
        embeddings = embeddings[sorted_idx]
        emb = embeddings.view(N, M, D)
        emb = self._l2_normalize(emb, self.eps)

        # Clamp w to be positive
        w = self.w.clamp(min=1e-6)

        if self.variant == "softmax":
            loss = self._softmax_loss(emb, N, M, D, w)
        else:
            loss = self._contrast_loss(emb, N, M, D, w)

        return loss

    def _softmax_loss(
        self,
        emb: torch.Tensor,
        N: int,
        M: int,
        D: int,
        w: torch.Tensor,
    ) -> torch.Tensor:
        total_loss = torch.zeros(1, device=emb.device, dtype=emb.dtype)

        for j in range(M):
            # Centroid for each speaker excluding utterance j
            centroids = torch.stack(
                [self._centroid(emb, exclude_idx=j) for _ in range(1)], dim=0
            ).squeeze(0)
            # Actually compute centroids properly: (N, D)
            centroids = torch.stack(
                [self._centroid(emb[[n]], exclude_idx=j).squeeze(0) for n in range(N)],
                dim=0,
            )
            centroids = self._l2_normalize(centroids, self.eps)  # (N, D)

            # Similarities: utterance j from each speaker vs all centroids
            # emb[:, j, :]: (N, D); centroids: (N, D)
            # sim[n, k] = cos_sim(emb[n,j], centroid[k])
            e_j = emb[:, j, :]  # (N, D)
            sim = torch.mm(e_j, centroids.t())  # (N, N)
            sim = w * sim + self.b

            # Target: diagonal (each speaker matches its own centroid)
            targets = torch.arange(N, device=emb.device)
            loss_j = F.cross_entropy(sim, targets)
            total_loss = total_loss + loss_j

        return total_loss / M

    def _contrast_loss(
        self,
        emb: torch.Tensor,
        N: int,
        M: int,
        D: int,
        w: torch.Tensor,
    ) -> torch.Tensor:
        total_loss = torch.zeros(1, device=emb.device, dtype=emb.dtype)

        for n in range(N):
            for j in range(M):
                # Centroid for speaker n excluding utterance j
                centroid_n = self._centroid(emb[[n]], exclude_idx=j).squeeze(0)
                centroid_n = self._l2_normalize(centroid_n.unsqueeze(0), self.eps).squeeze(0)

                e_nj = emb[n, j]  # (D,)

                # Positive similarity
                sim_pos = w * torch.dot(e_nj, centroid_n) + self.b

                # Negative similarities: centroids of all other speakers
                neg_sims = []
                for k in range(N):
                    if k == n:
                        continue
                    centroid_k = emb[k].mean(dim=0)
                    centroid_k = self._l2_normalize(centroid_k.unsqueeze(0), self.eps).squeeze(0)
                    neg_sims.append(w * torch.dot(e_nj, centroid_k) + self.b)

                if not neg_sims:
                    continue

                neg_sims_tensor = torch.stack(neg_sims)
                # Contrast loss: sigmoid on positive, sigmoid on negatives
                loss_pos = torch.sigmoid(-sim_pos)
                loss_neg = torch.sigmoid(neg_sims_tensor).sum()
                total_loss = total_loss + loss_pos + loss_neg

        return total_loss / (N * M)


class ContrastiveSpeakerLoss(nn.Module):
    """
    Contrastive / triplet-based speaker loss for fine-tuning a speaker encoder.

    Combines:
    - Contrastive loss: pulls same-speaker pairs together, pushes different-speaker
      pairs apart beyond a margin.
    - Optional online hard triplet mining for improved convergence.

    Args:
        margin: Minimum desired distance between negative pairs.
        use_triplet: If True, use triplet loss instead of pairwise contrastive.
        triplet_margin: Margin for triplet loss.
        distance: "cosine" or "euclidean".
        eps: Numerical stability constant.
    """

    def __init__(
        self,
        margin: float = 0.2,
        use_triplet: bool = False,
        triplet_margin: float = 0.3,
        distance: Literal["cosine", "euclidean"] = "cosine",
        eps: float = 1e-8,
    ) -> None:
        super().__init__()
        self.margin = margin
        self.use_triplet = use_triplet
        self.triplet_margin = triplet_margin
        self.distance = distance
        self.eps = eps

    def _cosine_distance_matrix(self, x: torch.Tensor) -> torch.Tensor:
        """Pairwise cosine distances in [0, 2]. Shape: (B, B)."""
        x_norm = F.normalize(x, p=2, dim=-1)
        sim = torch.mm(x_norm, x_norm.t())  # (B, B) in [-1, 1]
        return 1.0 - sim  # distance in [0, 2]

    def _euclidean_distance_matrix(self, x: torch.Tensor) -> torch.Tensor:
        """Pairwise squared Euclidean distances. Shape: (B, B)."""
        sq = (x ** 2).sum(dim=-1, keepdim=True)
        dist_sq = sq + sq.t() - 2.0 * torch.mm(x, x.t())
        return dist_sq.clamp(min=0.0).sqrt()

    def _pairwise_distances(self, embeddings: torch.Tensor) -> torch.Tensor:
        if self.distance == "cosine":
            return self._cosine_distance_matrix(embeddings)
        return self._euclidean_distance_matrix(embeddings)

    def _contrastive_loss(
        self,
        embeddings: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
        dist = self._pairwise_distances(embeddings)  # (B, B)
        B = embeddings.size(0)

        same = labels.unsqueeze(0) == labels.unsqueeze(1)   # (B, B) bool
        diff = ~same

        # Mask diagonal
        eye = torch.eye(B, dtype=torch.bool, device=embeddings.device)
        same = same & ~eye

        # Positive loss: pull same-speaker pairs together
        pos_loss = (dist[same] ** 2).mean() if same.any() else torch.zeros(1, device=embeddings.device).squeeze()

        # Negative loss: push different-speaker pairs apart
        neg_dist = dist[diff]
        neg_loss = F.relu(self.margin - neg_dist).pow(2).mean() if diff.any() else torch.zeros(1, device=embeddings.device).squeeze()

        return pos_loss + neg_loss

    def _triplet_loss(
        self,
        embeddings: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
        """Online hard triplet mining."""
        dist = self._pairwise_distances(embeddings)  # (B, B)
        B = embeddings.size(0)

        same = (labels.unsqueeze(0) == labels.unsqueeze(1))
        diff = ~same
        eye = torch.eye(B, dtype=torch.bool, device=embeddings.device)

        loss_total = torch.zeros(1, device=embeddings.device)
        count = 0

        for anchor_idx in range(B):
            # Hard positive: same-class, furthest
            pos_mask = same[anchor_idx] & ~eye[anchor_idx]
            if not pos_mask.any():
                continue
            d_pos = dist[anchor_idx][pos_mask].max()

            # Hard negative: different-class, closest
            neg_mask = diff[anchor_idx]
            if not neg_mask.any():
                continue
            d_neg = dist[anchor_idx][neg_mask].min()

            loss_total = loss_total + F.relu(d_pos - d_neg + self.triplet_margin)
            count += 1

        if count == 0:
            return torch.zeros(1, device=embeddings.device).squeeze()
        return (loss_total / count).squeeze()

    def forward(
        self,
        embeddings: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            embeddings: Speaker embeddings of shape (B, D).
            labels: Integer speaker IDs of shape (B,).

        Returns:
            Scalar loss tensor.
        """
        if self.use_triplet:
            return self._triplet_loss(embeddings, labels)
        return self._contrastive_loss(embeddings, labels)
