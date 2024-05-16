import tskit
import os
from ts_processors import *
import torch
from ts_simulators import *
import numpy as np

datadir = snakemake.params.datadir
num_simulations = snakemake.params.num_simulations
rounds = snakemake.params.rounds

with open(f"{datadir}/round_{rounds}/{num_simulations}.trees", "rb") as ts_file:
    ts = tskit.load(ts_file)

if snakemake.params.ts_processor == "dinf":
    processor = dinf_extract(snakemake)
elif snakemake.params.ts_processor == "three_channel_feature_matrices":
    processor = three_channel_feature_matrices(snakemake)
elif snakemake.params.ts_processor == "tskit_sfs":
    processor = tskit_sfs(snakemake)
elif snakemake.params.ts_processor == "tskit_sfs_selection":
    processor = tskit_sfs_selection(snakemake)

x = processor(ts)
# x is tensor, so change it to numpy first and save it as .npy
x = x.squeeze().cpu().numpy()
np.save(f"{datadir}/round_{rounds}/x_{num_simulations}.npy",x)
