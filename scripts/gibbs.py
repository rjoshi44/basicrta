from basicrta import *
from multiprocessing import Pool, Lock
from basicrta import istarmap
import numpy as np
import MDAnalysis as mda
import os 
from tqdm import tqdm

if __name__ == "__main__":
    # Parts of code taken from Shep (Centrifuge3.py, SuperMCMC.py)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--contacts')
    parser.add_argument('--top')
    parser.add_argument('--ncore')
    parser.add_argument('--resids', nargs='?')
    args = parser.parse_args()
    a = np.load(args.contacts)

    with open('contacts.metadata', 'r') as data:
        line = data.readlines()[1].split(',')
        trajlen, protlen, liplen, sel, ts = int(line[0]), int(line[1]), int(line[2]), line[3], float(line[4])

    nproc = int(args.ncore)
    u = mda.Universe(args.top)
    ids = u.select_atoms('protein').residues.resids
    names = u.select_atoms('protein').residues.resnames
    names = np.array([mda.lib.util.convert_aa_code(name) for name in names])
    uniqs = np.unique(a[:, 0]).astype(int)
    resids, resnames = ids[uniqs], names[uniqs]
    residues = np.array([f'{name}{resid}' for name, resid in zip(resnames, resids)])
    times = np.array([a[a[:, 0] == i][:, 3] for i in uniqs], dtype=object)
    trajtimes = np.array([a[a[:, 0] == i][:, 2] for i in uniqs], dtype=object)

    if args.resids:
        idinds = np.array([np.where(resids == resid)[0] for resid in resids])
        residues, times, trajtimes = residues[idinds], times[idinds], trajtimes[idinds]

    if not os.path.exists('BaSiC-RTA'):
        os.mkdir('BaSiC-RTA')
    os.chdir('BaSiC-RTA')

    input_list = np.array([[residues[i], times[i], ts] for i in range(len(residues))], dtype=object)
    with Pool(nproc, initializer=tqdm.set_lock, initargs=(Lock(),)) as p:
        for _ in tqdm(p.istarmap(run_residue, input_list), total=len(residues), position=0, desc='overall progress'):
            pass

    rem_inds = get_remaining_residue_inds(residues)
    times, trajtimes = times[rem_inds], trajtimes[rem_inds]

    residues, t_slow, sd, indicators = collect_results()
    plot_protein(residues, t_slow, sd)
    check_results(residues, times, ts)
    plot_hists(times, indicators, residues)

    # print(residues[0])
    # input_list = np.array([[u, times[i], trajtimes[i], indicators[i], residues[i]] for i in range(len(residues))],
    #                       dtype=object)
    # input_list = np.array([[u, times[i], trajtimes[i], indicators[i], residues[i]] for i in range(1)],
    #                       dtype=object)
    # Pool(nproc, initializer=tqdm.set_lock, initargs=(Lock(),)).starmap(write_trajs, input_list)

    # write_trajs(u, times, trajtimes, indicators, residues)
