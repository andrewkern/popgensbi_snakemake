import dinf
import torch
import numpy as np

class BaseProcessor:
    def __init__(self, snakemake, params_default):
        for key, default in params_default.items():
            if key in snakemake.params.keys():
                setattr(self, key, snakemake.params[key])
            else:
                setattr(self, key, default) 
        

class dinf_extract(BaseProcessor):
    params_default = {
        "n_snps": 500,
        "ploidy": 2,
        "phased": False,
        "maf_thresh": 0.05
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, dinf_extract.params_default)

    def __call__(self, ts):        
        '''
        input : tree sequence of one population
        output : genotype matrix + positional encoding (dinf's format)
        '''
        if self.ploidy == 2:
            if self.phased == False:
                n_sample = int(ts.num_samples / self.ploidy)
            else:
                n_sample = ts.num_samples
        elif self.ploidy == 1:
            n_sample = ts.num_samples
            
        extractor = dinf.feature_extractor.HaplotypeMatrix(
            num_individuals=n_sample, 
            num_loci=self.n_snps,
            ploidy=self.ploidy,
            phased=self.phased,
            maf_thresh=self.maf_thresh
        )
        feature_matrix = extractor.from_ts(ts)
        return torch.from_numpy(feature_matrix).float().permute(2, 0, 1)

class dinf_extract_multiple_pops(BaseProcessor):
    params_default = {
        "n_snps": 500,
        "ploidy": 2,
        "phased": False,
        "maf_thresh": 0.05
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, dinf_extract.params_default)

    def __call__(self, ts):        
        '''
        input : tree sequence of one population
        output : genotype matrix + positional encoding (dinf's format)
        '''
        from dinf.misc import ts_individuals
        # recover population names and corresponding sampled individuals
        pop_names = [pop.metadata['name'] for pop in ts.populations()]
        # make a dictionary with sampled individuals for each population except for unsampled ones
        sampled_pop_names = [pop for pop in pop_names if len(ts_individuals(ts, pop)) > 0]
        individuals = {name: ts_individuals(ts, name) for name in sampled_pop_names}
        num_individuals = {name: len(individuals[name]) for name in sampled_pop_names}

            
        extractor = dinf.feature_extractor.MultipleHaplotypeMatrices(
            num_individuals=num_individuals, 
            num_loci={pop: self.n_snps for pop in sampled_pop_names},
            ploidy={pop: self.ploidy for pop in sampled_pop_names},
            global_phased=self.phased,
            global_maf_thresh=self.maf_thresh
        )
        # we get a dictionary of feature matrices, one for each population
        feature_matrices = extractor.from_ts(ts, individuals=individuals)

        # Each feature matrix has dimension of (num_individual, num_loci, 2). 
        # because num_individual can be different for each population, we need to pad them with -1
        max_num_individuals = max([num_individuals[pop] for pop in sampled_pop_names])

        for pop in individuals.keys():
            feature_matrices[pop] = torch.from_numpy(feature_matrices[pop])
            num_individuals = feature_matrices[pop].shape[0]
            if num_individuals < max_num_individuals:
                feature_matrices[pop] = torch.nn.functional.pad(feature_matrices[pop], (0, 0, 0, 0, 0, max_num_individuals - num_individuals), "constant", -1)

        output_mat = torch.stack([v for v in feature_matrices.values()]).permute(0, 3, 1, 2)
        return output_mat


class three_channel_feature_matrices(BaseProcessor):
    params_default = {
        "n_snps": 500,
        "maf_thresh": 0.05
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, three_channel_feature_matrices.params_default)

    def __call__(self, ts):

        # genotype matrix (gm) shape = (total number of variants, number of individuals * 2 (for dipoid))
            gm = ts.genotype_matrix()
            positions = np.array(ts.tables.sites.position)
            # threshold by MAF
            ac0 = np.sum(gm == 0, axis=1)
            ac1 = np.sum(gm == 1, axis=1)
            keep = np.minimum(ac0, ac1) >= self.maf_thresh * gm.shape[1]
            gm = gm[keep]
            positions = positions[keep]
            # mut_type = 0 for neutral site, 1 for non-neutral site
            # If there are multiple mutations at a site, the last mutation is considered
            mut_types = np.array(
            [int(ts.site(i).mutations[0].metadata['mutation_list'][-1]['mutation_type'] > 1) for i in np.where(keep)[0]]
            )
            # trim or pad with zeros to resize gm to be (n_snps, num_individuals * 2)
            delta = gm.shape[0] - self.n_snps
            first_position = ts.site(0).position

            if delta >= 0:
                left = delta // 2
                right = left + self.n_snps
                gm = gm[left:right]
                positions = positions[left:right]
                delta_positions = np.diff(positions, prepend = first_position)
                mut_types = mut_types[left:right]
            else:
                pad_left = -delta // 2
                pad_right = self.n_snps - gm.shape[0] - pad_left
                gm_left = np.zeros((pad_left, gm.shape[1]), dtype = gm.dtype)
                gm_right = np.zeros((pad_right, gm.shape[1]), dtype = gm.dtype)
                gm = np.concatenate((gm_left, gm, gm_right))

                positions_left = np.zeros(pad_left, dtype = positions.dtype)
                right_pad_value = 0 if len(positions) == 0 else positions[-1]
                positions_right = np.full(pad_right, right_pad_value, dtype = positions.dtype)
                positions = np.concatenate((positions_left, positions, positions_right))
                delta_positions = np.diff(positions, prepend = positions[0])

                # pad mut_types with zeros
                mut_types_left = np.zeros(pad_left)
                mut_types_right = np.zeros(pad_right)
                mut_types = np.concatenate((mut_types_left, mut_types, mut_types_right))
                
            delta_positions = delta_positions / ts.sequence_length 
            # tile positional information vector to match the shape of gm
            # shape of delta_position_matrix = (num_individuals * 2, n_snps)
            delta_positions_matrix = np.tile(delta_positions, [gm.shape[1], 1])

            feature_matrix = np.zeros(shape = (gm.shape[1], self.n_snps, 3))
            feature_matrix[..., 0] = gm.T
            # tile positional information vector to match the shape of gm.T
            feature_matrix[..., 1] = np.tile(delta_positions, [gm.shape[1], 1])
            # same thing for mut_types
            feature_matrix[..., 2] = np.tile(mut_types, [gm.shape[1], 1])

            return torch.from_numpy(feature_matrix).float().permute(2, 0, 1)


class tskit_sfs(BaseProcessor):
    '''
    Normalized sfs (sum to 1)
    '''
    params_default = {
        "sample_sets": None,
        "windows": None,
        "mode": "site",
        "span_normalise": False,
        "polarised": False
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, tskit_sfs.params_default)
    def __call__(self, ts):
        sfs = ts.allele_frequency_spectrum(
            sample_sets = self.sample_sets, 
            windows = self.windows, 
            mode = self.mode, 
            span_normalise = self.span_normalise, 
            polarised = self.polarised)
        sfs = sfs / sum(sfs)
        return torch.from_numpy(sfs).float()

class tskit_jsfs(BaseProcessor):
    '''
    Joint site frequency spectrum for two-population model
    Normalized sfs (sum to 1)
    '''
    params_default = {
        "windows": None,
        "mode": "site",
        "span_normalise": False,
        "polarised": False
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, tskit_sfs.params_default)
    def __call__(self, ts):
        sfs = ts.allele_frequency_spectrum(
            sample_sets = [ts.samples(population=i) for i in range(ts.num_populations) if len(ts.samples(population=i))>0], 
            windows = self.windows, 
            mode = self.mode, 
            span_normalise = self.span_normalise, 
            polarised = self.polarised)
        sfs = sfs / sum(sum(sfs))
        return torch.from_numpy(sfs).float()




class tskit_sfs_selection(BaseProcessor):
    ## get SFS with synnonymous and non-synonymous mutations separately and append the two arrays to get a single array
    params_default = {
        "span_normalise": True,
        "polarised": False
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, tskit_sfs_selection.params_default)
    def __call__(self, ts):
        nonsyn_counts = []
        syn_counts = []
        for var in ts.variants():
            count = sum(var.genotypes)
            # If there are multiple mutations at a site, the last mutation is considered
            if var.site.mutations[-1].metadata['mutation_list'][-1]['mutation_type']==2:
                if self.polarised:
                    nonsyn_counts.append(min(count, ts.num_samples - count))
                else:
                    nonsyn_counts.append(count)
            else:
                if self.polarised:
                    syn_counts.append(min(count, ts.num_samples - count))
                else:
                    syn_counts.append(count)
        
        # compute span normalized SFS (length = ts.num_samples + 1 like in tskit)
        nonsyn_sfs = np.histogram(nonsyn_counts, bins = np.arange(-0.5, ts.num_samples + 1.5))[0]
        syn_sfs = np.histogram(syn_counts, bins = np.arange(-0.5, ts.num_samples + 1.5))[0]

        if self.span_normalise:
            nonsyn_sfs = nonsyn_sfs / ts.sequence_length
            syn_sfs = syn_sfs / ts.sequence_length
        
        sfs_combined = np.append(nonsyn_sfs, syn_sfs)
        return torch.from_numpy(sfs_combined).float()


class moments_LD_stats(BaseProcessor):
    '''
    create a matrix of recombination bin edges, LD statistics from moments from ts
    '''
    params_default = {
        "n_bins": 10,
        "n_snps": 5000, # number of rows in genotype matrix is max (n_snps, actual number of SNPs in ts)
        "n_avg": 5, # number of times to sample SNPs from ts,
        "phased": False # if true, we use a haplotype matrix (0 and 1) to calculate LD stats, if false, we use genotype matrix with 0, 1, and 2.
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, moments_LD_stats.params_default)
    def __call__(self, ts):
        import moments
        positions = np.array(ts.tables.sites.position)
        pos_bins = np.logspace(1, np.log10(ts.sequence_length) - 1, num=self.n_bins, base=10)
        n = 0

        # using dinf's misc function, ts_individuals, to check which populations have sampled individuals
        from dinf.misc import ts_individuals
        num_sampled_populations = 0
        sampled_pop_ids = []
        for pop in ts.populations():
            if len(ts_individuals(ts, pop.metadata['name']) > 0):
                num_sampled_populations += 1
                sampled_pop_ids.append(pop.id)
        output = np.zeros((len(pos_bins)-1) * 8 * (num_sampled_populations + num_sampled_populations * (num_sampled_populations - 1) // 2))

        while n < self.n_avg:
            n += 1
            # downsample SNPs if n_snps is smaller than the actual number of SNPs
            if len(positions) > self.n_snps:
                downsample_inds = np.random.choice(range(len(positions)), self.n_snps, replace=False)
                positions = positions[downsample_inds]
            # otherwise, use all SNPs
            else:
                downsample_inds = range(len(positions))                
            distances = []
            for i in range(len(positions)-1):
                for j in range(i+1, len(positions)):
                    distances.append(positions[j] - positions[i])
            
            inds = np.digitize(distances, pos_bins)
            # make a genotype matrix that is just 0 or 1 (ancestral v.s. derived)
            Gs = [(ts.genotype_matrix(samples=ts.samples(population=i))[downsample_inds,  :] > 0.5).astype(float)
                            for i in sampled_pop_ids]
            if self.phased == False:
                # if not phased, sum odd and even rows to get genotype of each individual (not each haplotype) = 0, 1 or 2
                Gs = [Gs[i][:, ::2] + Gs[i][:, 1::2] for i in range(num_sampled_populations)]

                # First compute stats within each population
            for i in range(num_sampled_populations):
                if self.phased:
                    D2_pw, Dz_pw, pi2_pw, D_pw = moments.LD.Parsing.compute_pairwise_stats(Gs[i], genotypes=False)
                else:
                    D2_pw, Dz_pw, pi2_pw, D_pw = moments.LD.Parsing.compute_pairwise_stats(Gs[i], genotypes=True)
                D2_pw_binned_mean = np.zeros(len(pos_bins)-1)
                D2_pw_binned_var = np.zeros(len(pos_bins)-1)
                Dz_pw_binned_mean = np.zeros(len(pos_bins)-1)
                Dz_pw_binned_var = np.zeros(len(pos_bins)-1)
                pi2_pw_binned_mean = np.zeros(len(pos_bins)-1)
                pi2_pw_binned_var = np.zeros(len(pos_bins)-1)
                D_pw_binned_mean = np.zeros(len(pos_bins)-1)
                D_pw_binned_var = np.zeros(len(pos_bins)-1)
                for j in range(len(pos_bins)-1):
                    D2_pw_binned_mean[j] = np.mean(D2_pw[inds==j+1])
                    D2_pw_binned_var[j] = np.var(D2_pw[inds==j+1])
                    Dz_pw_binned_mean[j] = np.mean(Dz_pw[inds==j+1])
                    Dz_pw_binned_var[j] = np.var(Dz_pw[inds==j+1])
                    pi2_pw_binned_mean[j] = np.mean(pi2_pw[inds==j+1])
                    pi2_pw_binned_var[j] = np.var(pi2_pw[inds==j+1])
                    D_pw_binned_mean[j] = np.mean(D_pw[inds==j+1])
                    D_pw_binned_var[j] = np.var(D_pw[inds==j+1])
                output[(len(pos_bins)-1)*8*i:(len(pos_bins)-1)*(8*i+1)] += D2_pw_binned_mean
                output[(len(pos_bins)-1)*(8*i+1):(len(pos_bins)-1)*(8*i+2)] += D2_pw_binned_var
                output[(len(pos_bins)-1)*(8*i+2):(len(pos_bins)-1)*(8*i+3)] += Dz_pw_binned_mean
                output[(len(pos_bins)-1)*(8*i+3):(len(pos_bins)-1)*(8*i+4)] += Dz_pw_binned_var
                output[(len(pos_bins)-1)*(8*i+4):(len(pos_bins)-1)*(8*i+5)] += pi2_pw_binned_mean
                output[(len(pos_bins)-1)*(8*i+5):(len(pos_bins)-1)*(8*i+6)] += pi2_pw_binned_var
                output[(len(pos_bins)-1)*(8*i+6):(len(pos_bins)-1)*(8*i+7)] += D_pw_binned_mean
                output[(len(pos_bins)-1)*(8*i+7):(len(pos_bins)-1)*(8*i+8)] += D_pw_binned_var

            # there are more unique pairs of SNPs when there are more than 1 population
            # so we need a new inds array
            distances = []
            for i in range(len(positions)):
                for j in range(len(positions)):
                    distances.append(positions[j] - positions[i])
            
            inds = np.digitize(distances, pos_bins)


            if num_sampled_populations > 1:
                pop_pair_idx = 0
                # If there are more than 1 population, compute stats between populations
                for i in range(num_sampled_populations):
                    for j in range(i+1, num_sampled_populations):
                        if self.phased:
                            D2_pw, Dz_pw, pi2_pw, D_pw = moments.LD.Parsing.compute_pairwise_stats_between(Gs[i], Gs[j], genotypes=False)
                        else:
                            D2_pw, Dz_pw, pi2_pw, D_pw = moments.LD.Parsing.compute_pairwise_stats_between(Gs[i], Gs[j], genotypes=True)
                        D2_pw_binned_mean = np.zeros(len(pos_bins)-1)
                        D2_pw_binned_var = np.zeros(len(pos_bins)-1)
                        Dz_pw_binned_mean = np.zeros(len(pos_bins)-1)
                        Dz_pw_binned_var = np.zeros(len(pos_bins)-1)
                        pi2_pw_binned_mean = np.zeros(len(pos_bins)-1)
                        pi2_pw_binned_var = np.zeros(len(pos_bins)-1)
                        D_pw_binned_mean = np.zeros(len(pos_bins)-1)
                        D_pw_binned_var = np.zeros(len(pos_bins)-1)
                        for k in range(len(pos_bins)-1):
                            D2_pw_binned_mean[k] = np.mean(D2_pw[inds==k+1])
                            D2_pw_binned_var[k] = np.var(D2_pw[inds==k+1])
                            Dz_pw_binned_mean[k] = np.mean(Dz_pw[inds==k+1])
                            Dz_pw_binned_var[k] = np.var(Dz_pw[inds==k+1])
                            pi2_pw_binned_mean[k] = np.mean(pi2_pw[inds==k+1])
                            pi2_pw_binned_var[k] = np.var(pi2_pw[inds==k+1])
                            D_pw_binned_mean[k] = np.mean(D_pw[inds==k+1])
                            D_pw_binned_var[k] = np.var(D_pw[inds==k+1])
                        
                        output[(len(pos_bins)-1)*8*(num_sampled_populations+pop_pair_idx):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+1)] += D2_pw_binned_mean
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+1):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+2)] += D2_pw_binned_var
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+2):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+3)] += Dz_pw_binned_mean
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+3):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+4)] += Dz_pw_binned_var
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+4):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+5)] += pi2_pw_binned_mean
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+5):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+6)] += pi2_pw_binned_var
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+6):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+7)] += D_pw_binned_mean
                        output[(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+7):(len(pos_bins)-1)*(8*(num_sampled_populations+pop_pair_idx)+8)] += D_pw_binned_var
                        pop_pair_idx += 1
        output /= self.n_avg
        return torch.from_numpy(output).float()

import os
import moments

def get_ld_stats(seg_idx, datadir, ts_processor, ts, seg_len, randn, rec_map_file, popfile, pops, r_bins):
    vcf_name = os.path.join(datadir, ts_processor, "{0}_seg_{1}.vcf".format(randn, seg_idx))
    site_mask = np.ones(ts.num_sites, dtype=bool)
    # unmask segments we want
    for site in ts.sites():
        if site.position > seg_idx * seg_len:
            if site.position < (seg_idx + 1) * seg_len:
                site_mask[site.id] = 0
    with open(vcf_name, "w+") as fout:
        ts.write_vcf(fout, site_mask=site_mask)
    os.system(f"gzip {vcf_name}")
    ld_stat = moments.LD.Parsing.compute_ld_statistics(
        str(vcf_name)+'.gz',
        rec_map_file=os.path.join(datadir, rec_map_file),
        pop_file=os.path.join(datadir, popfile),
        pops=pops,
        r_bins=r_bins,
        report=True)
    os.system("rm " + str(vcf_name)+'.gz')
    os.system("rm " + str(vcf_name)[:-3] + "h5")
    return ld_stat

class moments_LD_stats2(BaseProcessor):
    '''
    second version of LD stats processor. Uses moments.LD.Parsing.compute_ld_statistics
    '''
    params_default = {
        "rec_map_file":"rec_map_file.txt",
        "pop_file":"pop_file.txt",
        "pops":["deme0", "deme1"],
        "r_bins":[0, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5, 1e-4, 2e-4, 5e-4, 1e-3],
        "n_segs":100,
    }
    def __init__(self, snakemake):
        super().__init__(snakemake, moments_LD_stats2.params_default)
        self.datadir = snakemake.params.datadir
        self.ts_processor = snakemake.params.ts_processor
        self.randn = np.random.randint(0, 9999999)

    def __call__(self, ts):
        import moments
        import os
        import multiprocessing
        from functools import partial        
        # get the length of each segment
        seg_len = int(ts.sequence_length / self.n_segs)
        partial_process = partial(get_ld_stats, 
                datadir = self.datadir, 
                ts_processor = self.ts_processor, 
                ts = ts, 
                seg_len = seg_len, 
                randn = self.randn, 
                rec_map_file = self.rec_map_file, 
                popfile = self.pop_file, 
                pops = self.pops, 
                r_bins = self.r_bins)

        from multiprocessing import Pool
        args = list(range(self.n_segs))
        # args = [(item,) for item in args]
        p = Pool(10)
        ld_stats = p.map(partial_process, args, chunksize=max(1, self.n_segs//10))
        ld_stats_dict = {}
        for i in range(len(ld_stats)):
            ld_stats_dict[i] = ld_stats[i]
        stats = ld_stats_dict[0]["stats"]
        means = moments.LD.Parsing.means_from_region_data(ld_stats_dict, stats)
        output = []
        # will stack means of D2, Dz and pi2 and append replicate of H
        for i in range(len(means)-1):
            output.append(means[i])

        rep = len(output[0])
        for i in range(len(means[-1])):
            output.append(np.repeat(means[-1][i], rep))
        output = np.stack(output)
        return torch.from_numpy(output).float()
        



PROCESSOR_LIST = {
    "dinf": dinf_extract,
    "dinf_multiple_pops": dinf_extract_multiple_pops,
    "three_channel_feature_matrices": three_channel_feature_matrices,
    "tskit_sfs": tskit_sfs,
    "tskit_jsfs": tskit_jsfs,
    "tskit_sfs_selection": tskit_sfs_selection, 
    "moments_LD_stats": moments_LD_stats,
    "moments_LD_stats2": moments_LD_stats2
}