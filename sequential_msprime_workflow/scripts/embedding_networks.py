import numpy as np
import torch
from torch import nn
from sbi.neural_nets.embedding_nets import *

class SymmetricLayer(nn.Module):
    """
    Layer that performs some permutation-invariant function along a
    specified axis of input data.

    The permuation invariant function can be any of max, mean, or sum
    """

    def __init__(self, axis, func="max"):
        super().__init__()
        self.axis = axis
        self.func = func

    def forward(self, x):
        if self.func == "max":
            return torch.max(x, dim=self.axis, keepdim=True)[0]
        elif self.func == "mean":
            return torch.mean(x, dim=self.axis, keepdim=True)
        elif self.func == "sum":
            return torch.sum(x, dim=self.axis, keepdim=True)
        else:
            raise ValueError("func must be one of 'max', 'mean', or 'sum'")


class ExchangeableCNN(nn.Module):
    """
    This implements the Exchangeable CNN or permuation-invariant CNN from:
        Chan et al. 2018, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7687905/

    which builds in the invariance of the haplotype matrices to permutations of the individuals

    If input features come from multiple populations that may differ in num_snps and/or
    num_individuals, then provide a list of tuples with each populations haplotype matrix
    shape in unmasked_x_shps. The forward pass will then mask out all padded values of -1
    which pad each haplotype matrix to the shape of the largest in the set
    """

    def __init__(self, latent_dim=5, unmasked_x_shps=None, channels=2, symmetric_func="max"):
        """
        :param latent_dim: The desired dimension of the final 1D output vector
            to be used as the embedded data for training
        :param unmasked_x_shps: This is the shapes of each populations feature matrix
            before being padded. Needs to be given if we have mutliple differently sized
            feature matrices for different populations
        :param channels: The number of channels in the input matrices. HaplotypeMatrices
            have 2 channels and BinnedHaplotypeMatrices have 1 channel
        :param symmetric_func: String denoting which symmetric function to use in our
            permutation invariant layers
        """
        super().__init__()
        self.sizes1 = (32, 64)
        self.sizes2 = (64,)
        self.cnn_kernel_size = (1, 5)
        self.activation = nn.ELU
        self.unmasked_x_shps = unmasked_x_shps
        feat_ext_inp_dim = 64 if unmasked_x_shps is None else 64 * len(unmasked_x_shps)
        cnn_layers = []
        for in_size, feature_size in zip([channels, *self.sizes1], self.sizes1):
            cnn_layers.append(
                nn.Conv2d(
                    in_size,
                    feature_size,
                    self.cnn_kernel_size,
                    stride=(1, 2),
                    bias=False,
                )
            )
            cnn_layers.append(self.activation())
            cnn_layers.append(nn.BatchNorm2d(num_features=feature_size))
        cnn_layers.append(SymmetricLayer(axis=2, func=symmetric_func))
        for feature_size in self.sizes2:
            cnn_layers.append(
                nn.Conv2d(
                    feature_size,
                    feature_size,
                    self.cnn_kernel_size,
                    stride=(1, 2),
                    bias=False,
                )
            )
            cnn_layers.append(self.activation())
            cnn_layers.append(nn.BatchNorm2d(num_features=feature_size))
        cnn_layers.append(SymmetricLayer(axis=3, func=symmetric_func))
        self.cnn = nn.Sequential(*cnn_layers)
        self.feature_extractor = nn.Sequential(
            nn.Flatten(),
            nn.Linear(feat_ext_inp_dim, 64),
            nn.ReLU(),
            nn.Linear(64, latent_dim),
        )

    def __call__(self, x):
        # if unmasked_x_shps is not None this means we have mutliple populations and
        # thus could have padded values of -1 we want to make sure to choose a mask
        # that pulls out all values of the different populations feature matrices,
        # EXCEPT those that equal -1
        if self.unmasked_x_shps is not None and len(x.shape) == 5:
            xs = []
            batch_ndim = x.shape[0]
            for i, shape in enumerate(self.unmasked_x_shps):
                mask = x[:, i, :, :, :] != -1
                inds = torch.where(mask)
                x_ = x[:, i, :, :, :][inds].view(batch_ndim, *shape)
                xs.append(self.cnn(x_))
            x = torch.cat(xs, dim=-1)
            return self.feature_extractor(x)
        # Otherwise we know there are no padded values and can just run the
        # input data through the network
        return self.feature_extractor(self.cnn(x))
    
    def embedding(self, x):
        with torch.no_grad():
            if self.unmasked_x_shps is not None and len(x.shape) == 5:
                xs = []
                batch_ndim = x.shape[0]
                for i, shape in enumerate(self.unmasked_x_shps):
                    mask = x[:, i, :, :, :] != -1
                    inds = torch.where(mask)
                    x_ = x[:, i, :, :, :][inds].view(batch_ndim, *shape)
                    xs.append(self.cnn(x_))
                x = torch.cat(xs, dim=-1)
                return self.feature_extractor[:2](x)
            return self.feature_extractor[:2](self.cnn(x))
