from __future__ import division

# LIBTBX_SET_DISPATCHER_NAME prime.solve_indexing_ambiguity
"""
Author      : Uervirojnangkoorn, M.
Created     : 8/15/2016
Description : Command line for solving indexing ambiguity
"""
import os, sys
import numpy as np
from libtbx.easy_mp import pool_map
from prime.index_ambiguity.mod_indexing_ambiguity import indamb_handler
import cPickle as pickle
from prime.index_ambiguity.mod_kmeans import kmeans_handler
from prime.postrefine.mod_mx import mx_handler
from prime.command_line.genref import genref_handler
from prime.command_line.merge import merge_handler
import random


def solve_with_mtz_mproc(args):
    frame_no, pickle_filename, iparams, miller_array_ref = args
    idah = indamb_handler()
    index_basis, txt_out = idah.calc_cc(
        frame_no, pickle_filename, iparams, miller_array_ref
    )
    print txt_out
    return pickle_filename, index_basis


def calculate_r_mproc(args):
    frame_no, pickle_filename, index_basis, obs_main, obs_list = args
    idah = indamb_handler()
    r_set, txt_out = idah.calc_r(
        frame_no, pickle_filename, index_basis, obs_main, obs_list
    )
    print txt_out
    return pickle_filename, index_basis, r_set


def get_obs_mproc(args):
    frame_no, pickle_filename, iparams = args
    idah = indamb_handler()
    alt_dict = idah.get_observations(pickle_filename, iparams)
    return alt_dict, pickle_filename


class indexing_ambiguity_handler(object):
    def __init__(self):
        """Intialize parameters."""

    def get_twin_operators(self, obs):
        idah = indamb_handler()
        return idah.generate_twin_operators(obs_in)

    def should_terminate(self, iparams, pickle_filename):
        # if no indexing ambiguity problem detected and mode is not set to "Forced"
        idah = indamb_handler()
        alt_dict = idah.get_observations(pickle_filename, iparams)
        if len(alt_dict.keys()) == 1 and iparams.indexing_ambiguity.mode != "Forced":
            return True
        if (
            iparams.indexing_ambiguity.mode == "Forced"
            and len(iparams.indexing_ambiguity.assigned_basis) == 0
        ):
            return True
        return False

    def run(self, args):
        # read inputs
        from prime.postrefine.mod_input import process_input, read_pickles

        iparams, txt_out_input = process_input(args)
        print txt_out_input
        f = open(iparams.run_no + "/log.txt", "w")
        f.write(txt_out_input)
        f.close()
        # if solution pickle is given, return the file name
        if iparams.indexing_ambiguity.index_basis_in is not None:
            if iparams.indexing_ambiguity.index_basis_in.endswith(".pickle"):
                return iparams.indexing_ambiguity.index_basis_in, iparams
        # read all integration pickles
        frame_files = read_pickles(iparams.data)
        n_frames = len(frame_files)
        if n_frames == 0:
            print "No integration pickle found. Exit program."
            return None, iparams
        # exit if no problem
        if self.should_terminate(iparams, frame_files[0]):
            print "No indexing ambiguity problem. Set index_ambiguity.mode = Forced and assigned_basis = list of basis formats to solve pseudo-twinning problem."
            return None, iparams
        # continue with (Auto - alt>1, find solution), (Auto - alt>1, mtz)
        # (Forced - assigned_basis, mtz), (Forced - assigned_basis, find solution)
        # *************************************************
        # if mtz file is given, use it to solve the problem
        sol_fname = iparams.run_no + "/index_ambiguity/solution_pickle.pickle"
        if iparams.indexing_ambiguity.index_basis_in is not None:
            if iparams.indexing_ambiguity.index_basis_in.endswith(".mtz"):
                mxh = mx_handler()
                flag_ref_found, miller_array_ref = mxh.get_miller_array_from_reflection_file(
                    iparams.indexing_ambiguity.index_basis_in
                )
                if flag_ref_found == False:
                    print "Reference mtz file not found. Set indexing_ambiguity.index_basis_in = None to enable auto generate the solutions."
                    return None, iparams
                else:
                    frames = [
                        (i, frame_files[i], iparams, miller_array_ref)
                        for i in range(n_frames)
                    ]
                    cc_results = pool_map(
                        iterable=frames,
                        func=solve_with_mtz_mproc,
                        processes=iparams.n_processors,
                    )
                    sol_pickle = {}
                    for result in cc_results:
                        pickle_filename, index_basis = result
                        sol_pickle[pickle_filename] = index_basis
                    pickle.dump(sol_pickle, open(sol_fname, "wb"))
                    return sol_fname, iparams
        # *************************************************
        # solve with Brehm & Diederichs - sample size n_sample_frames then bootstrap the rest
        frames = [
            (i, frame_files[i], iparams)
            for i in random.sample(
                range(n_frames), iparams.indexing_ambiguity.n_sample_frames
            )
        ]
        # get observations list
        print "Reading observations"
        alt_dict_results = pool_map(
            iterable=frames, func=get_obs_mproc, processes=iparams.n_processors
        )
        frame_dup_files = []
        frame_keys = []
        obs_list = []
        for result in alt_dict_results:
            alt_dict, pickle_filename = result
            if alt_dict is not None:
                for key in alt_dict.keys():
                    frame_dup_files.append(pickle_filename)
                    frame_keys.append(key)
                    obs_list.append(alt_dict[key])
        frames = [
            (i, frame_dup_files[i], frame_keys[i], obs_list[i], obs_list)
            for i in range(len(frame_dup_files))
        ]
        # calculate r
        print "Calculating R"
        calc_r_results = pool_map(
            iterable=frames, func=calculate_r_mproc, processes=iparams.n_processors
        )
        frame_dup_files = []
        frame_keys = []
        r_matrix = []
        for result in calc_r_results:
            if result is not None:
                pickle_filename, index_basis, r_set = result
                frame_dup_files.append(pickle_filename)
                frame_keys.append(index_basis)
                if len(r_matrix) == 0:
                    r_matrix = r_set
                else:
                    r_matrix = np.append(r_matrix, r_set, axis=0)
        # choose groups with best CC
        print "Selecting frames with best R"
        i_mean_r = np.argsort(np.mean(r_matrix, axis=1))[::-1]
        r_matrix_sorted = r_matrix[i_mean_r]
        frame_dup_files_sorted = np.array(frame_dup_files)[i_mean_r]
        frame_keys_sorted = np.array(frame_keys)[i_mean_r]
        frame_dup_files_sel = []
        for frame_file, frame_key, r_set in zip(
            frame_dup_files_sorted, frame_keys_sorted, r_matrix_sorted
        ):
            if frame_file not in frame_dup_files_sel:
                frame_dup_files_sel.append(frame_file)
                print frame_file, frame_key, np.mean(r_set)
                if (
                    len(frame_dup_files_sel)
                    >= iparams.indexing_ambiguity.n_selected_frames
                ):
                    print "Found all %6.0f good frames" % (len(frame_dup_files_sel))
                    break
        ##
        # rebuild observations and r_matrix
        frames = [
            (i, frame_dup_files_sel[i], iparams)
            for i in range(len(frame_dup_files_sel))
        ]
        # get observations list
        print "Re-reading observations"
        alt_dict_results = pool_map(
            iterable=frames, func=get_obs_mproc, processes=iparams.n_processors
        )
        frame_dup_files = []
        frame_keys = []
        obs_list = []
        for result in alt_dict_results:
            alt_dict, pickle_filename = result
            if alt_dict is not None:
                for key in alt_dict.keys():
                    frame_dup_files.append(pickle_filename)
                    frame_keys.append(key)
                    obs_list.append(alt_dict[key])
        frames = [
            (i, frame_dup_files[i], frame_keys[i], obs_list[i], obs_list)
            for i in range(len(frame_dup_files))
        ]
        # calculate r
        print "Re-calculating R"
        calc_r_results = pool_map(
            iterable=frames, func=calculate_r_mproc, processes=iparams.n_processors
        )
        frame_dup_files = []
        frame_keys = []
        r_matrix = []
        for result in calc_r_results:
            if result is not None:
                pickle_filename, index_basis, r_set = result
                frame_dup_files.append(pickle_filename)
                frame_keys.append(index_basis)
                if len(r_matrix) == 0:
                    r_matrix = r_set
                else:
                    r_matrix = np.append(r_matrix, r_set, axis=0)
        print "Minimizing frame distance"
        idah = indamb_handler()
        x_set = idah.optimize(r_matrix, flag_plot=iparams.flag_plot)
        x_pickle = {
            "frame_dup_files": frame_dup_files,
            "frame_keys": frame_keys,
            "r_matrix": r_matrix,
            "x_set": x_set,
        }
        pickle.dump(x_pickle, open(iparams.run_no + "/index_ambiguity/x.out", "wb"))
        print "Clustering results"
        kmh = kmeans_handler()
        k = 2 ** (len(idah.get_observations(frame_dup_files[0], iparams)) - 1)
        centroids, labels = kmh.run(x_set, k, flag_plot=iparams.flag_plot)
        print "Get solution pickle"
        sample_fname = iparams.run_no + "/index_ambiguity/sample.lst"
        sol_pickle = idah.assign_basis(
            frame_dup_files, frame_keys, labels, k, sample_fname
        )
        pickle.dump(sol_pickle, open(sol_fname, "wb"))
        # if more frames found, merge the sample frames to get a reference set
        # that can be used for breaking the ambiguity.
        if n_frames > iparams.indexing_ambiguity.n_selected_frames:
            print "Breaking the indexing ambiguity for the remaining images."
            old_iparams_data = iparams.data[:]
            iparams.data = [sample_fname]
            iparams.indexing_ambiguity.index_basis_in = sol_fname
            grh = genref_handler()
            grh.run_by_params(iparams)
            mh = merge_handler()
            mh.run_by_params(iparams)
            DIR = iparams.run_no + "/mtz/"
            file_no_list = [int(fname.split(".")[0]) for fname in os.listdir(DIR)]
            if len(file_no_list) > 0:
                hklref_indamb = DIR + str(max(file_no_list)) + ".mtz"
                print "Bootstrap reference reflection set:", hklref_indamb
                # setup a list of remaining frames
                frame_files_remain = []
                for frame in frame_files:
                    if frame not in sol_pickle:
                        frame_files_remain.append(frame)
                # determine index basis
                mxh = mx_handler()
                flag_ref_found, miller_array_ref = mxh.get_miller_array_from_reflection_file(
                    hklref_indamb
                )
                frames = [
                    (i, frame_files_remain[i], iparams, miller_array_ref)
                    for i in range(len(frame_files_remain))
                ]
                cc_results = pool_map(
                    iterable=frames,
                    func=solve_with_mtz_mproc,
                    processes=iparams.n_processors,
                )
                for result in cc_results:
                    pickle_filename, index_basis = result
                    sol_pickle[pickle_filename] = index_basis
            iparams.data = old_iparams_data[:]
        # write out solution pickle
        pickle.dump(sol_pickle, open(sol_fname, "wb"))
        # write out text output
        txt_out = (
            "Solving indexing ambiguity complete. Solution file saved to "
            + sol_fname
            + "\n"
        )
        f = open(iparams.run_no + "/log.txt", "a")
        f.write(txt_out)
        f.close()
        return sol_fname, iparams


if __name__ == "__main__":
    idah = indexing_ambiguity_handler()
    idah.run(sys.argv[1:] if len(sys.argv) > 1 else None)
