import stdpopsim
from process_ts import dinf_extract
import torch
from sbi.utils import BoxUniform

class AraTha_2epoch_simulator:
    def __init__(self, 
                n_sample=10, 
                n_snps=2000, 
                maf_thresh=0.05, 
                N_A_true=746148,
                N_0_true=100218,
                t_1_true=56834,
                mutation_rate_true=7e-9, 
                N_A_low=10_000,
                N_A_high=1_000_000,
                N_0_low=10_000,
                N_0_high=1_000_000,
                t_1_low=1_000,
                t_1_high=1_000_000,
                mutation_rate_low=0,
                mutation_rate_high=1.0e-8
                ):
        self.n_sample = n_sample
        self.n_snps = n_snps
        self.maf_thresh = maf_thresh
        self.true_values = {"N_A": N_A_true, "N_0": N_0_true, "t_1": t_1_true, "mutation_rate": mutation_rate_true}
        self.bounds = {"N_A": (N_A_low, N_A_high),
                        "N_0": (N_0_low, N_0_high),
                        "t_1": (t_1_low, t_1_high),
                        "mutation_rate": (mutation_rate_low, mutation_rate_high),
                        }
        low = [self.bounds[p][0] for p in self.bounds.keys()]
        high = [self.bounds[p][1] for p in self.bounds.keys()]
        self.prior = BoxUniform(low=torch.tensor(low), high=torch.tensor(high), device="cuda" if torch.cuda.is_available() else "cpu")

    def __call__(self, theta):
        N_A, N_0, t_1, mutation_rate = theta.squeeze().cpu().tolist()

        species = stdpopsim.get_species("AraTha")
        contig = species.get_contig(length=10e6, mutation_rate=mutation_rate)
        model = stdpopsim.PiecewiseConstantSize(N_A, (t_1, N_0))
        engine = stdpopsim.get_engine("msprime")

        ts = engine.simulate(model, contig, samples={"pop_0": self.n_sample})
        ploidy = 2
        phased = False
        result = dinf_extract(ts, self.n_sample, self.n_snps, ploidy, phased, self.maf_thresh)

        return result