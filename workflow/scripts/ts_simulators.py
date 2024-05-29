import stdpopsim
import torch
from sbi.utils import BoxUniform
import numpy as np

class BaseSimulator:
    def __init__(self, snakemake, params_default):
        for key, default in params_default.items():
            if key in snakemake.params.keys():
                setattr(self, key, snakemake.params[key])
            else:
                setattr(self, key, default)
            
## ts_simulators outputs tree sequence. This cannot be used as a simulator for simulate_for_sbi!
class AraTha_2epoch_simulator(BaseSimulator):
    species = stdpopsim.get_species("AraTha")
    model = species.get_demographic_model("African2Epoch_1H18")
    params_default = {
        "n_sample": 10,
        "N_A_true": model.model.events[0].initial_size,
        "N_0_true": model.populations[0].initial_size,
        "t_1_true": model.model.events[0].time,
        "mutation_rate_true": model.mutation_rate,
        "N_A_low": 10_000,
        "N_A_high": 1_000_000,
        "N_0_low": 10_000,
        "N_0_high": 1_000_000,
        "t_1_low": 1_000,
        "t_1_high": 1_000_000,
        "mutation_rate_low": 0,
        "mutation_rate_high": 1.0e-8,
        "contig_length": 10e6,
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, AraTha_2epoch_simulator.params_default)

        self.true_values = {"N_A": self.N_A_true, "N_0": self.N_0_true, "t_1": self.t_1_true, "mutation_rate": self.mutation_rate_true}
        self.bounds = {"N_A": (self.N_A_low, self.N_A_high),
                        "N_0": (self.N_0_low, self.N_0_high),
                        "t_1": (self.t_1_low, self.t_1_high),
                        "mutation_rate": (self.mutation_rate_low, self.mutation_rate_high),
                        }
        low = [self.bounds[p][0] for p in self.bounds.keys()]
        high = [self.bounds[p][1] for p in self.bounds.keys()]
        self.prior = BoxUniform(low=torch.tensor(low), high=torch.tensor(high), device="cuda" if torch.cuda.is_available() else "cpu")

    def __call__(self, theta):
        if type(theta) is torch.Tensor:
            N_A, N_0, t_1, mutation_rate = theta.squeeze().cpu().tolist()
        elif type(theta) is list:
            N_A, N_0, t_1, mutation_rate = theta
        
        species = AraTha_2epoch_simulator.species
        contig = species.get_contig(length=self.contig_length, mutation_rate=mutation_rate)
        model = AraTha_2epoch_simulator.model
        model.populations[0].initial_size = N_0
        model.model.events[0].initial_size = N_A
        model.model.events[0].time = t_1
        engine = stdpopsim.get_engine("msprime")

        ts = engine.simulate(model, contig, samples={"SouthMiddleAtlas": self.n_sample})

        return ts

class HomSap_Africa_1b08_simulator(BaseSimulator):
    species = stdpopsim.get_species("HomSap")
    model = species.get_demographic_model("Africa_1B08")
    params_default = {
        "n_sample": 10,
        "N_A_true": model.model.events[0].initial_size,
        "N_0_true": model.populations[0].initial_size,
        "t_1_true": model.model.events[0].time,
        "mutation_rate_true": model.mutation_rate,
        "N_A_low": 100,
        "N_A_high": 30_000,
        "N_0_low": 100,
        "N_0_high": 30_000,
        "t_1_low": 10,
        "t_1_high": 10_000,
        "mutation_rate_low": 0,
        "mutation_rate_high": 4.0e-8,
        "contig_length": 10e6,
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, HomSap_Africa_1b08_simulator.params_default)
        self.true_values = {"N_A": self.N_A_true, "N_0": self.N_0_true, "t_1": self.t_1_true, "mutation_rate": self.mutation_rate_true}
        self.bounds = {"N_A": (self.N_A_low, self.N_A_high),
                        "N_0": (self.N_0_low, self.N_0_high),
                        "t_1": (self.t_1_low, self.t_1_high),
                        "mutation_rate": (self.mutation_rate_low, self.mutation_rate_high),
                        }
        low = [self.bounds[p][0] for p in self.bounds.keys()]
        high = [self.bounds[p][1] for p in self.bounds.keys()]
        self.prior = BoxUniform(low=torch.tensor(low), high=torch.tensor(high), device="cuda" if torch.cuda.is_available() else "cpu")

    def __call__(self, theta):
        if type(theta) is torch.Tensor:
            N_A, N_0, t_1, mutation_rate = theta.squeeze().cpu().tolist()
        elif type(theta) is list:
            N_A, N_0, t_1, mutation_rate = theta
        
        species = HomSap_Africa_1b08_simulator.species
        contig = species.get_contig(length=self.contig_length, mutation_rate=mutation_rate)
        model = HomSap_Africa_1b08_simulator.model
        model.populations[0].initial_size = N_0
        model.model.events[0].initial_size = N_A
        model.model.events[0].time = t_1
        engine = stdpopsim.get_engine("msprime")
        ts = engine.simulate(model, contig, samples={"African_Americans": self.n_sample})

        return ts

class gammaDFE_cnst_N_simulator(BaseSimulator):
    species = stdpopsim.get_species("HomSap")
    contig = species.get_contig('chr1', left=0, right=1e6)
    dfe = species.get_dfe("Gamma_K17")
    params_default = {
        "n_sample": 100,
        "mutation_rate_true": contig.mutation_rate,
        "shape_true": dfe.mutation_types[1].distribution_args[1],
        "mean_true": dfe.mutation_types[1].distribution_args[0],
        "p_true": dfe.proportions[1] / sum(dfe.proportions),
        "mutation_rate_low": 1e-8,
        "mutation_rate_high": 3e-8,
        "shape_low": 0.01,
        "shape_high": 1.,
        "mean_low": -0.05,
        "mean_high": 0.,
        "p_low": 0.6,
        "p_high": 0.8,
        "N": 10000
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, gammaDFE_cnst_N_simulator.params_default)
        self.true_values = {"mutation_rate": self.mutation_rate_true, "mean": self.mean_true, "shape": self.shape_true, "p": self.p_true}
        self.bounds = {"mutation_rate": (self.mutation_rate_low, self.mutation_rate_high),
                        "mean": (self.mean_low, self.mean_high),
                        "shape": (self.shape_low, self.shape_high),
                        "p": (self.p_low, self.p_high),
                        }
        low = [self.bounds[p][0] for p in self.bounds.keys()]
        high = [self.bounds[p][1] for p in self.bounds.keys()]
        self.prior = BoxUniform(low=torch.tensor(low), high=torch.tensor(high), device="cuda" if torch.cuda.is_available() else "cpu")

    def __call__(self, theta):
        if type(theta) is torch.Tensor:
            mutation_rate, mean, shape, p = theta.squeeze().cpu().tolist()
        elif type(theta) is list:
            mutation_rate, mean, shape, p = theta
        
        species = gammaDFE_cnst_N_simulator.species
        contig = gammaDFE_cnst_N_simulator.contig
        contig.mutation_rate = mutation_rate

        dfe = gammaDFE_cnst_N_simulator.dfe
        dfe.mutation_types[1].distribution_args = [mean, shape]
        dfe.proportions = [1-p, p]
        contig.add_dfe(intervals=np.array([[0, int(contig.length)]]), DFE=dfe)
        model = stdpopsim.PiecewiseConstantSize(self.N)
        engine = stdpopsim.get_engine("slim")

        ts = engine.simulate(model, contig, samples={"pop_0": self.n_sample})

        return ts

class AnaPla_split_migration_simulator(BaseSimulator):
    species = stdpopsim.get_species("AnaPla")
    model = species.get_demographic_model("MallardBlackDuck_2L19")
    params_default = {
        "samples": {"Mallard": 10, "Black_duck": 10}, 
        "N_A_true": model.populations[-1].initial_size, # ancestral population size
        "N_B_true": model.populations[0].initial_size, # Black duck population size
        "N_M_true": model.populations[1].initial_size, # Mallard population size
        "T_true": model.model.events[0].time, # split time
        "m_true": model.model.migration_matrix[0, 1], # migration rate
        "N_A_low": 1e3,
        "N_A_high": 1e7,
        "N_B_low": 1e3,
        "N_B_high": 1e7,
        "N_M_low": 1e3,
        "N_M_high": 1e7,
        "T_low": 1e3,
        "T_high": 1e7,
        "m_low": 0,
        "m_high": 1e-1,
        "contig_length": 1e6
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, AnaPla_split_migration_simulator.params_default)
        self.true_values = {"N_A": self.N_A_true, "N_B": self.N_B_true, "N_M": self.N_M_true, "T": self.T_true, "m": self.m_true}
        self.bounds = {"N_A": (self.N_A_low, self.N_A_high),
                        "N_B": (self.N_B_low, self.N_B_high),
                        "N_M": (self.N_M_low, self.N_M_high),
                        "T": (self.T_low, self.T_high),
                        "m": (self.m_low, self.m_high),
                        }
        low = [self.bounds[p][0] for p in self.bounds.keys()]
        high = [self.bounds[p][1] for p in self.bounds.keys()]
        self.prior = BoxUniform(low=torch.tensor(low), high=torch.tensor(high), device="cuda" if torch.cuda.is_available() else "cpu")
    def __call__(self, theta):
        if type(theta) is torch.Tensor:
            N_A, N_B, N_M, T, m = theta.squeeze().cpu().tolist()
        elif type(theta) is list:
            N_A, N_B, N_M, T, m = theta
        
        model = AnaPla_split_migration_simulator.model
        model.populations[-1].initial_size = N_A
        model.populations[0].initial_size = N_B
        model.populations[1].initial_size = N_M
        model.model.events[0].time = T
        model.model.migration_matrix[0, 1] = m
        model.model.migration_matrix[1, 0] = m
        contig = self.species.get_contig(length=self.contig_length, mutation_rate=model.mutation_rate)
        engine = stdpopsim.get_engine("msprime")
        ts = engine.simulate(model, contig, samples=self.samples)
        return ts

class PonAbe_split_migration_simulator(BaseSimulator):
    species = stdpopsim.get_species("PonAbe")
    model = species.get_demographic_model("TwoSpecies_2L11")
    params_default = {
        "samples": {"Bornean":5,"Sumatran":5}, 
        "log10_N_A_true": np.log10(model.model.events[-1].initial_size), # ancestral population size
        "log10_T_true": np.log10(model.model.events[0].time), # split time
        "s_true": model.populations[0].initial_size * np.exp(-model.populations[0].growth_rate * model.model.events[0].time) / model.model.events[-1].initial_size, # proportion of Na to branch B
        "log10_N_B_true": np.log10(model.populations[0].initial_size), # current Bornean population size
        "log10_N_S_true": np.log10(model.populations[1].initial_size), # current Sumatran population size
        "log10_m_B_S_true": np.log10(model.model.migration_matrix[0, 1]), # migration rate Bornean to Sumatran
        "log10_m_S_B_true": np.log10(model.model.migration_matrix[1, 0]), # migration rate Sumatran to Bornean
        "log10_N_A_low": 3,
        "log10_N_A_high": 6,
        "log10_N_B_low": 3,
        "log10_N_B_high": 6,
        "log10_N_S_low": 3,
        "log10_N_S_high": 6,
        "log10_T_low": 3,
        "log10_T_high": 6,
        "log10_m_B_S_low": -9,
        "log10_m_B_S_high": -3,
        "log10_m_S_B_low": -9,
        "log10_m_S_B_high": -3,
        "s_low": 0.01,
        "s_high": 0.99,
        "contig_length": 1960000
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, PonAbe_split_migration_simulator.params_default)
        self.true_values = {"log10_N_A": self.log10_N_A_true, 
            "log10_N_B": self.log10_N_B_true, 
            "log10_N_S": self.log10_N_S_true, 
            "log10_T": self.log10_T_true, 
            "log10_m_B_S": self.log10_m_B_S_true, 
            "log10_m_S_B": self.log10_m_S_B_true, 
            "s": self.s_true}
        self.bounds = {"log10_N_A": (self.log10_N_A_low, self.log10_N_A_high),
                        "log10_N_B": (self.log10_N_B_low, self.log10_N_B_high),
                        "log10_N_S": (self.log10_N_S_low, self.log10_N_S_high),
                        "log10_T": (self.log10_T_low, self.log10_T_high),
                        "log10_m_B_S": (self.log10_m_B_S_low, self.log10_m_B_S_high),
                        "log10_m_S_B": (self.log10_m_S_B_low, self.log10_m_S_B_high),
                        "s": (self.s_low, self.s_high)
                        }
        low = [self.bounds[p][0] for p in self.bounds.keys()]
        high = [self.bounds[p][1] for p in self.bounds.keys()]
        self.prior = BoxUniform(low=torch.tensor(low), high=torch.tensor(high), device="cuda" if torch.cuda.is_available() else "cpu")
    def __call__(self, theta):
        if type(theta) is torch.Tensor:
            log10_N_A, log10_N_B, log10_N_S, log10_T, log10_m_B_S, log10_m_S_B, s = theta.squeeze().cpu().tolist()
        elif type(theta) is list:
            log10_N_A, log10_N_B, log10_N_S, log10_T, log10_m_B_S, log10_m_S_B, s = theta
        N_A = 10 ** log10_N_A
        N_B = 10 ** log10_N_B
        N_S = 10 ** log10_N_S
        T = 10 ** log10_T
        m_B_S = 10 ** log10_m_B_S
        m_S_B = 10 ** log10_m_S_B

        model = PonAbe_split_migration_simulator.model
        model.model.events[-1].initial_size = N_A
        model.populations[0].initial_size = N_B
        model.populations[1].initial_size = N_S
        for i in range(len(model.model.events)):
            model.model.events[i].time = T
        r_B = -1 * np.log(s * N_A / N_B) / T
        r_S = -1 * np.log((1-s) * N_A / N_S) / T
        model.populations[0].growth_rate = r_B
        model.populations[1].growth_rate = r_S
        model.model.migration_matrix[0, 1] = m_B_S
        model.model.migration_matrix[1, 0] = m_S_B
        contig = self.species.get_contig(length=self.contig_length, mutation_rate=model.mutation_rate)
        engine = stdpopsim.get_engine("msprime")
        ts = engine.simulate(model, contig, samples=self.samples)
        return ts


MODEL_LIST = {
    "AraTha_2epoch": AraTha_2epoch_simulator,
    "HomSap_2epoch": HomSap_Africa_1b08_simulator,
    "gammaDFE_cnst_N": gammaDFE_cnst_N_simulator,
    "AnaPla_split_migration": AnaPla_split_migration_simulator,
    "PonAbe_split_migration": PonAbe_split_migration_simulator
}