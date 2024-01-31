"""Analysis functions
"""

import os
import gc
import pickle

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from numpy.random import default_rng
from tqdm import tqdm
from scipy import stats
from sklearn.cluster import KMeans

gc.enable()
mpl.rcParams['pdf.fonttype'] = 42
rng = default_rng()


class Gibbs(object):
    """Gibbs sampler to estimate parameters of an exponential mixture for a set 
    of data. Results are stored in gibbs.results, which uses /home/ricky
    MDAnalysis.analysis.base.Results(). If 'results=None' the gibbs sampler has
    not been executed, which requires calling '.run()'
    
    """

    def __init__(self, times=None, residue=None, loc=0, ncomp=15, niter=50000):
        self.times, self.residue = times, residue
        self.niter, self.loc, self.ncomp = niter, loc, ncomp
        self.results, self.g, self.burnin = None, 100, 10000

        if times:
            diff = (np.sort(times)[1:]-np.sort(times)[:-1])
            self.ts = diff[diff != 0][0]
        else:
            self.ts = None

    def __str__(self):
        return f'Gibbs sampler'

    def __call__(self):
        print('call')

    def _prepare(self):
        from basicrta.util import get_s
        self.t, self.s = get_s(self.times, self.ts)

        if not os.path.exists(f'{self.residue}'):
            os.mkdir(f'{self.residue}')

        # initialize arrays
        self.indicator = np.memmap(f'{self.residue}/.indicator_{self.niter}.npy',
                                   shape=((self.niter + 1) // g, x.shape[0]), mode='w+',
                                   dtype=np.uint8)
        self.mcweights = np.zeros(((self.niter + 1) // g, self.ncomp))
        self.mcrates = np.zeros(((self.niter + 1) // g, self.ncomp))

        # guess hyperparameters
        self.whypers = np.ones(self.ncomp) / [self.ncomp]
        self.rhypers = np.ones((self.ncomp, 2)) * [1, 3]


    def run(self):
        # initialize weights and rates
        inrates = 0.5 * 10 ** np.arange(-self.ncomp + 2, 2, dtype=float)
        tmpw = 9 * 10 ** (-np.arange(1, self.ncomp + 1, dtype=float))
        weights, rates = tmpw / tmpw.sum(), inrates[::-1]

        # gibbs sampler
        for j in tqdm(range(1, self.niter+1),
                      desc=f'{self.residue}-K{self.ncomp}',
                      position=self.loc, leave=False):

            # compute probabilities
            tmp = weights*rates*np.exp(np.outer(-rates,x)).T
            z = (tmp.T/tmp.sum(axis=1)).T
        
            # sample indicator
            s = np.argmax(rng.multinomial(1, z), axis=1)
            
            # get indicator for each data point
            inds = [np.where(s == i)[0] for i in range(self.ncomp)]

            # compute total time and number of point for each component
            Ns = np.array([len(inds[i]) for i in range(self.ncomp)])
            Ts = np.array([self.times[inds[i]].sum() for i in range(self.ncomp)])

            # sample posteriors
            weights = rng.dirichlet(self.whypers+Ns)
            rates = rng.gamma(self.rhypers[:, 0]+Ns, 1/(self.rhypers[:, 1]+Ts))

            # save every g steps
            if j%g==0:
                ind = j//g-1
                self.mcweights[ind], self.mcrates[ind] = weights, rates
                self.indicator[ind] = s

        attrs = ["mcweights", "mcrates", "ncomp", "niter", "s", "t", "residue",
                 "times"]
        values = [self.mcweights, self.mcrates, self.ncomp, self.niter, self.s,
                  self.t, self.residue, self.times]
        
        r = self._save_results(attrs, values)
        self.results = r


    def _process_gibbs(self, cutoff=1e-4):
        burnin_ind = self.burnin // self.g

        inds = np.where(self.mcweights[burnin_ind:] > cutoff)
        indices = np.arange(self.burnin, self.niter + 1, self.g)[inds[0]] // self.g
        lens = [len(row[row > cutoff]) for row in self.mcweights[burnin_ind:]]
        ncomp = stats.mode(lens, keepdims=False)[0]

        weights = self.mcweights[burnin_ind::][inds]
        rates = self.mcrates[burnin_ind::][inds]

        data = np.stack((weights, rates), axis=1)
        km = KMeans(n_clusters=ncomp).fit(np.log(data))
        Indicator = np.zeros((self.times.shape[0], ncomp))
        indicator = np.memmap(f'{self.residue}/.indicator_{self.niter}.npy',
                              shape=((self.niter + 1) // self.g, self.times.shape[0]),
                              mode='r', dtype=np.uint8)

        for j in np.unique(inds[0]):
            mapinds = km.labels_[inds[0] == j]
            for i, indx in enumerate(inds[1][inds[0] == j]):
                tmpind = np.where(indicator[j] == indx)[0]
                Indicator[tmpind, mapinds[i]] += 1

        Indicator = (Indicator.T / Indicator.sum(axis=1)).T

        attrs = ["weights", "rates", "ncomp", "residue", "indicator", "labels",
                 "iteration", "niter"]
        values = [weights, rates, ncomp, self.residue, Indicator,
                  km.labels_, indices, self.niter]
        r = self._save_results(attrs, values, processed=True)
        return r


    def _save_results(self, attrs, values, processed=False):
        from MDAnalysis.analysis.base import Results
        r = Results()

        for attr, value in zip(attrs, values):
            setattr(r, attr, value)

        if processed:
            with open(f'{r.residue}/processed_results_{r.niter}.pkl',
                      'wb') as W:
                pickle.dump(r, W)
        else:
            with open(f'{r.residue}/results_{r.niter}.pkl', 'wb') as W:
                pickle.dump(r, W)

        return r


    def load_results(self, results):
        with open(results, 'r+b') as f:
            self.results = pickle.load(f)

        for attr in list(self.results.keys()):
            setattr(self, attr, self.results[f'{attr}'])


    def hist_results(self, scale=1.5, save=False):
        cmap = mpl.colormaps['tab20']
        rp = self._process_gibbs()

        fig, ax = plt.subplots(1, 2, figsize=(4*scale, 3*scale))
        [ax[0].hist(rp.weights[rp.labels == i],
                     bins=np.exp(np.linspace(np.log(rp.weights[rp.labels == i]
                                                    .min()),
                                             np.log(rp.weights[rp.labels == i]
                                                    .max()), 50)),
                    label=f'{i+1}', alpha=0.5, color=cmap(i))
         for i in range(rp.ncomp)]
        [ax[1].hist(rp.rates[rp.labels == i],
                    bins=np.exp(np.linspace(np.log(rp.rates[rp.labels == i]
                                                   .min()),
                                            np.log(rp.rates[rp.labels == i]
                                                   .max()), 50)),
                    label=f'{i+1}', alpha=0.5, color=cmap(i))
         for i in range(rp.ncomp)]
        ax[0].set_xscale('log')
        ax[1].set_xscale('log')
        ax[0].legend(title='component')
        ax[1].legend(title='component')
        ax[0].set_xlabel(r'weight')
        ax[1].set_xlabel(r'rate ($ns^{-1}$)')
        ax[0].set_ylabel('count')
        ax[0].set_xlim(1e-4, 1)
        ax[1].set_xlim(1e-3, 10)
        plt.tight_layout()
        if save:
            plt.savefig('hist_results.png', bbox_inches='tight')
            plt.savefig('hist_results.pdf', bbox_inches='tight')
        plt.show()


    def plot_results(self, scale=1.5, sparse=1, save=False):
            cmap = mpl.colormaps['tab20']
            rp = self._process_gibbs()

            fig, ax = plt.subplots(2, figsize=(4*scale, 3*scale), sharex=True)
            [ax[0].plot(rp.iteration[rp.labels == i][::sparse],
                        rp.weights[rp.labels == i][::sparse], '.',
                        label=f'{i+1}', color=cmap(i))
             for i in range(rp.ncomp)]
            ax[0].set_yscale('log')
            ax[0].set_ylabel(r'weight')
            [ax[1].plot(rp.iteration[rp.labels == i][::sparse],
                        rp.rates[rp.labels == i][::sparse], '.', label=f'{i+1}',
                        color=cmap(i)) for i in range(rp.ncomp)]
            ax[1].set_yscale('log')
            ax[1].set_ylabel(r'rate ($ns^{-1}$)')
            ax[1].set_xlabel('sample')
            ax[0].legend(title='component')
            ax[1].legend(title='component')
            plt.tight_layout()
            if save:
                plt.savefig('plot_results.png', bbox_inches='tight')
                plt.savefig('plot_results.pdf', bbox_inches='tight')
            plt.show()


if __name__ == '__main__':
    print('do nothing')