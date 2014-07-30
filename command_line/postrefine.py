from __future__ import division

# LIBTBX_SET_DISPATCHER_NAME prime.postrefine
"""
Author      : Uervirojnangkoorn, M.
Created     : 7/13/2014
Description : Commands linked to prime.postrefine libraries.
"""
import os, sys
from libtbx.easy_mp import pool_map
import numpy as np
from cctbx.array_family import flex
from datetime import datetime, time
import logging
import math

FORMAT = "%(levelname)s %(module)s.%(funcName)s: %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)


def determine_mean_I_mproc(frame_no, frame_files, iparams):
    from prime.postrefine import postref_handler

    prh = postref_handler()
    mean_I = prh.calc_mean_intensity(frame_files[frame_no], iparams)
    return mean_I


def scale_frame_by_mean_I_mproc(frame_no, frame_files, iparams, mean_of_mean_I):
    from prime.postrefine import postref_handler

    prh = postref_handler()
    pres = prh.scale_frame_by_mean_I(
        frame_no, frame_files[frame_no], iparams, mean_of_mean_I
    )
    return pres


def postrefine_by_frame_mproc(
    frame_no, frame_files, iparams, miller_array_ref, pres_results
):
    from prime.postrefine import postref_handler

    prh = postref_handler()
    if pres_results is None:
        pres_in = None
    else:
        pres_in = pres_results[frame_no]
    pres = prh.postrefine_by_frame(
        frame_no, frame_files[frame_no], iparams, miller_array_ref, pres_in
    )
    return pres


def calc_average_I_mproc(
    group_no,
    group_id_list,
    miller_indices_all,
    I_all,
    sigI_all,
    G_all,
    B_all,
    p_all,
    sin_theta_over_lambda_sq_all,
    SE_all,
    avg_mode,
    iparams,
):
    # select only this group
    i_sel = group_id_list == group_no
    miller_indices = miller_indices_all.select(i_sel)
    I = I_all.select(i_sel)
    sigI = sigI_all.select(i_sel)
    G = G_all.select(i_sel)
    B = B_all.select(i_sel)
    p = p_all.select(i_sel)
    sin_theta_over_lambda_sq = sin_theta_over_lambda_sq_all.select(i_sel)
    SE = SE_all.select(i_sel)

    from prime.postrefine import calc_avg_I

    result = calc_avg_I(
        group_no,
        miller_indices[0],
        I,
        sigI,
        G,
        B,
        p,
        sin_theta_over_lambda_sq,
        SE,
        avg_mode,
        iparams,
    )
    return result


def read_pickles(data):
    frame_files = []
    for pickle_dir in data:
        for file_name in os.listdir(pickle_dir):
            if file_name.endswith(".pickle"):
                frame_files.append(pickle_dir + "/" + file_name)

    # check if pickle_dir is given in input file instead of from cmd arguments.
    if len(frame_files) == 0:
        print "No pickle files found."
        exit()

    return frame_files


if __name__ == "__main__":
    logging.info("Starting process.")
    # capture starting time
    time_global_start = datetime.now()

    # 0 .read input parameters and frames (pickle files)
    from prime.postrefine import read_input

    iparams, txt_out_input = read_input(sys.argv[:1])
    print txt_out_input

    frame_files = read_pickles(iparams.data)
    frames = range(len(frame_files))

    # 1. prepare reference miller array
    txt_merge_mean = ""
    miller_array_ref = None
    # Always generate the mean-intensity scaled set.
    # Calculate <I> for each frame
    def determine_mean_I_mproc_wrapper(arg):
        return determine_mean_I_mproc(arg, frame_files, iparams)

    determine_mean_I_result = pool_map(
        args=frames, func=determine_mean_I_mproc_wrapper, processes=None
    )

    frames_mean_I = flex.double()
    for result in determine_mean_I_result:
        if result is not None:
            frames_mean_I.append(result)

    mean_of_mean_I = np.median(frames_mean_I)

    # use the calculate <mean_I> to scale each frame
    def scale_frame_by_mean_I_mproc_wrapper(arg):
        return scale_frame_by_mean_I_mproc(arg, frame_files, iparams, mean_of_mean_I)

    scale_frame_by_mean_I_result = pool_map(
        args=frames, func=scale_frame_by_mean_I_mproc_wrapper, processes=None
    )

    observations_merge_mean_set = []
    for pres in scale_frame_by_mean_I_result:
        if pres is not None:
            observations_merge_mean_set.append(pres)

    if len(observations_merge_mean_set) > 0:
        avg_mode = "average"
        from prime.postrefine import prepare_output

        prep_output = prepare_output(observations_merge_mean_set, iparams, avg_mode)

        if prep_output is not None:
            cn_group, group_id_list, miller_indices_all_sort, I_obs_all_sort, sigI_obs_all_sort, G_all_sort, B_all_sort, p_all_sort, sin_sq_all_sort, SE_all_sort, uc_mean, wavelength_mean, txt_prep_out = (
                prep_output
            )

            def calc_average_I_mproc_wrapper(arg):
                return calc_average_I_mproc(
                    arg,
                    group_id_list,
                    miller_indices_all_sort,
                    I_obs_all_sort,
                    sigI_obs_all_sort,
                    G_all_sort,
                    B_all_sort,
                    p_all_sort,
                    sin_sq_all_sort,
                    SE_all_sort,
                    avg_mode,
                    iparams,
                )

            calc_average_I_result = pool_map(
                args=range(cn_group), func=calc_average_I_mproc_wrapper, processes=None
            )

            miller_indices_merge = flex.miller_index()
            I_merge = flex.double()
            sigI_merge = flex.double()
            stat_all = []
            I_even = flex.double()
            I_odd = flex.double()
            for results in calc_average_I_result:
                if results is not None:
                    miller_index, I_avg, sigI_avg, stat, I_avg_even, I_avg_odd = results
                    if (
                        math.isnan(stat[0])
                        or math.isinf(stat[0])
                        or math.isnan(stat[1])
                        or math.isinf(stat[1])
                    ):
                        print miller_index, " not merged (Qw=%.4g/%.4g)" % (
                            stat[0],
                            stat[1],
                        )
                    else:
                        miller_indices_merge.append(miller_index)
                        I_merge.append(I_avg)
                        sigI_merge.append(sigI_avg)
                        stat_all.append(stat)
                        I_even.append(I_avg_even)
                        I_odd.append(I_avg_odd)

            from prime.postrefine import write_output

            miller_array_ref, txt_merge_mean, csv_merge_mean = write_output(
                miller_indices_merge,
                I_merge,
                sigI_merge,
                stat_all,
                I_even,
                I_odd,
                iparams,
                uc_mean,
                wavelength_mean,
                iparams.run_no + "/mean_scaled",
            )

            txt_merge_mean = txt_merge_mean + txt_prep_out
            print txt_merge_mean
            if iparams.flag_force_no_postrefine:
                txt_out = txt_out_input + txt_merge_mean
                f = open(iparams.run_no + "/log.txt", "w")
                f.write(txt_out)
                f.close()
                exit()

    if iparams.hklrefin is not None:
        # In case ref. intensity set is given, overwrite the reference set.
        from iotbx import reflection_file_reader

        reflection_file_ref = reflection_file_reader.any_reflection_file(
            iparams.hklrefin
        )
        miller_arrays_ref = reflection_file_ref.as_miller_arrays()
        is_found_ref_as_intensity_array = False
        is_found_ref_as_amplitude_array = False
        for miller_array in miller_arrays_ref:
            if miller_array.is_xray_intensity_array():
                miller_array_ref = miller_array.deep_copy()
                is_found_ref_as_intensity_array = True
                break
            elif miller_array.is_xray_amplitude_array():
                is_found_ref_as_amplitude_array = True
                miller_array_converted_to_intensity = miller_array.as_intensity_array()
        if is_found_ref_as_intensity_array == False:
            if is_found_ref_as_amplitude_array:
                miller_array_ref = miller_array_converted_to_intensity.deep_copy()

    if miller_array_ref is None:
        print "No reference intensity. Exit without post-refinement"
        exit()

    # 2. Post-refinement
    n_iters = iparams.n_postref_cycle
    txt_merge_postref = ""
    postrefine_by_frame_result = None
    for i in range(n_iters):
        txt_merge_postref += "Start post-refinement cycle " + str(i + 1) + "\n"
        print "Start post-refinement cycle " + str(i + 1) + "\n"
        print "Frame# Res.(A) N_refl N_refl_used  R_init R_final R_xy_init R_xy_final CC_init CC_final CCiso_init CCiso_final  Basis"
        print "------------------------------------------------------------------------------------------------------------------------"

        def postrefine_by_frame_mproc_wrapper(arg):
            return postrefine_by_frame_mproc(
                arg, frame_files, iparams, miller_array_ref, postrefine_by_frame_result
            )

        postrefine_by_frame_result = pool_map(
            args=frames, func=postrefine_by_frame_mproc_wrapper, processes=None
        )

        postrefine_by_frame_good = []
        for pres in postrefine_by_frame_result:
            if pres is not None:
                postrefine_by_frame_good.append(pres)

        if len(postrefine_by_frame_good) > 0:
            avg_mode = "weighted"
            from prime.postrefine import prepare_output

            prep_output = prepare_output(postrefine_by_frame_good, iparams, avg_mode)

            if prep_output is not None:
                cn_group, group_id_list, miller_indices_all_sort, I_obs_all_sort, sigI_obs_all_sort, G_all_sort, B_all_sort, p_all_sort, sin_sq_all_sort, SE_all_sort, uc_mean, wavelength_mean, txt_prep_out = (
                    prep_output
                )

                def calc_average_I_mproc_wrapper(arg):
                    return calc_average_I_mproc(
                        arg,
                        group_id_list,
                        miller_indices_all_sort,
                        I_obs_all_sort,
                        sigI_obs_all_sort,
                        G_all_sort,
                        B_all_sort,
                        p_all_sort,
                        sin_sq_all_sort,
                        SE_all_sort,
                        avg_mode,
                        iparams,
                    )

                calc_average_I_result = pool_map(
                    args=range(cn_group),
                    func=calc_average_I_mproc_wrapper,
                    processes=None,
                )

                miller_indices_merge = flex.miller_index()
                I_merge = flex.double()
                sigI_merge = flex.double()
                stat_all = []
                I_even = flex.double()
                I_odd = flex.double()
                for results in calc_average_I_result:
                    if results is not None:
                        miller_index, I_avg, sigI_avg, stat, I_avg_even, I_avg_odd = (
                            results
                        )
                        if (
                            math.isnan(stat[0])
                            or math.isinf(stat[0])
                            or math.isnan(stat[1])
                            or math.isinf(stat[1])
                        ):
                            print miller_index, " not merged (Qw=%.4g/%.4g)" % (
                                stat[0],
                                stat[1],
                            )
                        else:
                            miller_indices_merge.append(miller_index)
                            I_merge.append(I_avg)
                            sigI_merge.append(sigI_avg)
                            stat_all.append(stat)
                            I_even.append(I_avg_even)
                            I_odd.append(I_avg_odd)

                from prime.postrefine import write_output

                miller_array_pr, txt_merge_out, csv_out = write_output(
                    miller_indices_merge,
                    I_merge,
                    sigI_merge,
                    stat_all,
                    I_even,
                    I_odd,
                    iparams,
                    uc_mean,
                    wavelength_mean,
                    iparams.run_no + "/postref_cycle_" + str(i + 1),
                )

                miller_array_ref = miller_array_pr.deep_copy()

                txt_merge_postref += txt_merge_out + txt_prep_out
                print txt_merge_out
                print txt_prep_out
        else:
            print "No frames merged as a reference set - exit without post-refinement"
            exit()

    # collect caculating time
    time_global_end = datetime.now()
    time_global_spent = time_global_end - time_global_start
    txt_out_time_spent = (
        "Total calculation time: "
        + "{0:.2f}".format(time_global_spent.seconds)
        + " seconds\n"
    )
    print txt_out_time_spent

    txt_out = txt_out_input + txt_merge_mean + txt_merge_postref + txt_out_time_spent
    f = open(iparams.run_no + "/log.txt", "w")
    f.write(txt_out)
    f.close()
