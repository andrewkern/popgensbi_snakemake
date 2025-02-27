## Reproducing AraTha/Africa2Epoch_1h18 of popgensbi

import torch

import msprime
import stdpopsim
import os
import numpy as np
import pickle
from ts_simulators import *
from ts_processors import *

datadir = snakemake.params.datadir
tsname = snakemake.params.tsname
thetaname = snakemake.params.thetaname

if not os.path.isdir(f"{datadir}"):
    os.mkdir(f"{datadir}")

demog_model = snakemake.params.demog_model

simulator = MODEL_LIST[demog_model](snakemake)

theta = simulator.prior.sample((1,))

ts = simulator(theta)
with open(os.path.join(datadir, tsname), "wb") as ts_file:
    ts.dump(ts_file)
theta = theta.squeeze().cpu().numpy()
np.save(os.path.join(datadir, thetaname), theta)
