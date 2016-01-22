from __future__ import division

# LIBTBX_SET_DISPATCHER_NAME prime.print_integration_pickle
"""
Author      : Uervirojnangkoorn, M.
Created     : 11/1/2015
Description : read integration pickles and view systemetic absences and beam X, Y position
"""

import cPickle as pickle
from cctbx.array_family import flex
from iotbx import reflection_file_reader
import sys, os, math
from scitbx.matrix import sqr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab


def get_miller_array_from_mtz(mtz_filename):
    flag_hklisoin_found = False
    miller_array_iso = None
    if mtz_filename is not None:
        flag_hklisoin_found = True
        reflection_file_iso = reflection_file_reader.any_reflection_file(mtz_filename)
        miller_arrays_iso = reflection_file_iso.as_miller_arrays()
        is_found_iso_as_intensity_array = False
        is_found_iso_as_amplitude_array = False
        for miller_array in miller_arrays_iso:
            if miller_array.is_xray_intensity_array():
                miller_array_iso = miller_array.deep_copy()
                is_found_iso_as_intensity_array = True
                break
            elif miller_array.is_xray_amplitude_array():
                is_found_iso_as_amplitude_array = True
                miller_array_converted_to_intensity = miller_array.as_intensity_array()
        if is_found_iso_as_intensity_array == False:
            if is_found_iso_as_amplitude_array:
                miller_array_iso = miller_array_converted_to_intensity.deep_copy()
            else:
                flag_hklisoin_found = False

    if miller_array_iso is not None:
        perm = miller_array_iso.sort_permutation(by_value="resolution", reverse=True)
        miller_array_iso = miller_array_iso.select(perm)
    return flag_hklisoin_found, miller_array_iso


def read_pickles(data):
    frame_files = []
    for p in data:
        if os.path.isdir(p) == False:
            # check if list-of-pickle text file is given
            pickle_list_file = open(p, "r")
            pickle_list = pickle_list_file.read().split("\n")
            for pickle_filename in pickle_list:
                if os.path.isfile(pickle_filename):
                    frame_files.append(pickle_filename)
        else:
            for pickle_filename in os.listdir(p):
                if pickle_filename.endswith(".pickle"):
                    frame_files.append(p + "/" + pickle_filename)
    # check if pickle_dir is given in input file instead of from cmd arguments.
    if len(frame_files) == 0:
        print "No pickle files found."
        exit()
    return frame_files


def read_input(args):
    if len(args) == 0:
        print "prime.print_integration_pickle: for viewing systematic absences and beam xy position from integration pickles."
        print "usage: prime.print_integration_pickle data=integrated.lst pixel_size_mm=0.079346 check_sys_absent=True target_space_group=P212121"
        exit()
    data = []
    hklrefin = None
    pixel_size_mm = None
    check_sys_absent = False
    target_space_group = None
    target_anomalous_flag = False
    flag_plot = True
    d_min = 0
    d_max = 99
    for i in range(len(args)):
        pair = args[i].split("=")
        if pair[0] == "data":
            data.append(pair[1])
        if pair[0] == "hklrefin":
            hklrefin = pair[1]
        if pair[0] == "pixel_size_mm":
            pixel_size_mm = float(pair[1])
        if pair[0] == "check_sys_absent":
            check_sys_absent = bool(pair[1])
        if pair[0] == "target_space_group":
            target_space_group = pair[1]
        if pair[0] == "target_anomalous_flag":
            target_anomalous_flag = bool(pair[1])
        if pair[0] == "flag_plot":
            if pair[1] == "False":
                flag_plot = False
        if pair[0] == "d_min":
            d_min = float(pair[1])
        if pair[0] == "d_max":
            d_max = float(pair[1])
    if len(data) == 0:
        print "Please provide data path. (eg. data=/path/to/pickle/)"
        exit()
    if check_sys_absent:
        if target_space_group is None:
            print "Please provide target space group if you want to check systematic absence (eg. target_space_group=P212121)"
            exit()
    if pixel_size_mm is None:
        print "Please specify pixel size (eg. pixel_size_mm=0.079346)"
        exit()
    return (
        data,
        hklrefin,
        pixel_size_mm,
        check_sys_absent,
        target_space_group,
        target_anomalous_flag,
        flag_plot,
        d_min,
        d_max,
    )


if __name__ == "__main__":
    cc_bin_low_thres = 0.25
    beam_thres = 0.25
    # 0 .read input parameters and frames (pickle files)
    data, hklrefin, pixel_size_mm, check_sys_absent_input, target_space_group, target_anomalous_flag, flag_plot, d_min, d_max = read_input(
        args=sys.argv[1:]
    )
    frame_files = read_pickles(data)
    xbeam_set = flex.double()
    ybeam_set = flex.double()
    sys_abs_set = []
    sys_abs_all = flex.double()
    cc_bin_low_set = flex.double()
    cc_bins_set = []
    d_bins_set = []
    oodsqr_bins_set = []
    print "Summary of integration pickles:"
    print "(image file, min. res., max. res, beamx, beamy, n_refl, cciso, <cciso_bin>, a, b, c, mosaicity, residual)"
    for pickle_filename in frame_files:
        check_sys_absent = check_sys_absent_input
        observations_pickle = pickle.load(open(pickle_filename, "rb"))
        pickle_filename_arr = pickle_filename.split("/")
        pickle_filename_only = pickle_filename_arr[len(pickle_filename_arr) - 1]
        flag_hklisoin_found, miller_array_iso = get_miller_array_from_mtz(hklrefin)
        observations = observations_pickle["observations"][0]
        swap_dict = {"test_xx1.pickle": 0, "tes_xx2.pickle": 0}
        if pickle_filename_only in swap_dict:
            from cctbx import sgtbx

            cb_op = sgtbx.change_of_basis_op("a,c,b")
            observations = observations.change_basis(cb_op)
        # apply constrain using the crystal system
        if check_sys_absent:
            try:
                from cctbx.crystal import symmetry

                miller_set = symmetry(
                    unit_cell=observations.unit_cell().parameters(),
                    space_group_symbol=target_space_group,
                ).build_miller_set(
                    anomalous_flag=target_anomalous_flag, d_min=observations.d_min()
                )
                observations = observations.customized_copy(
                    anomalous_flag=target_anomalous_flag,
                    crystal_symmetry=miller_set.crystal_symmetry(),
                )
            except Exception:
                print "Cannot apply target space group: observed space group=", observations.space_group_info()
                check_sys_absent = False
        # calculate partiality
        wavelength = observations_pickle["wavelength"]
        crystal_init_orientation = observations_pickle["current_orientation"][0]
        detector_distance_mm = observations_pickle["distance"]
        mm_predictions = pixel_size_mm * (observations_pickle["mapped_predictions"][0])
        xbeam = observations_pickle["xbeam"]
        ybeam = observations_pickle["ybeam"]
        xbeam_set.append(xbeam)
        ybeam_set.append(ybeam)
        alpha_angle = flex.double(
            [
                math.atan(abs(pred[0] - xbeam) / abs(pred[1] - ybeam))
                for pred in mm_predictions
            ]
        )
        spot_pred_x_mm = flex.double([pred[0] - xbeam for pred in mm_predictions])
        spot_pred_y_mm = flex.double([pred[1] - ybeam for pred in mm_predictions])
        # resoultion filter
        i_sel_res = observations.resolution_filter_selection(d_min=d_min, d_max=d_max)
        observations = observations.select(i_sel_res)
        alpha_angle = alpha_angle.select(i_sel_res)
        spot_pred_x_mm = spot_pred_x_mm.select(i_sel_res)
        spot_pred_y_mm = spot_pred_y_mm.select(i_sel_res)
        # sort by resolution
        perm = observations.sort_permutation(by_value="resolution", reverse=True)
        observations = observations.select(perm)
        alpha_angle = alpha_angle.select(perm)
        spot_pred_x_mm = spot_pred_x_mm.select(perm)
        spot_pred_y_mm = spot_pred_y_mm.select(perm)
        from prime.postrefine.mod_leastsqr import calc_spot_radius

        r0 = calc_spot_radius(
            sqr(crystal_init_orientation.reciprocal_matrix()),
            observations.indices(),
            wavelength,
        )
        from prime.postrefine.mod_leastsqr import calc_partiality_anisotropy_set

        two_theta = observations.two_theta(wavelength=wavelength).data()
        sin_theta_over_lambda_sq = (
            observations.two_theta(wavelength=wavelength)
            .sin_theta_over_lambda_sq()
            .data()
        )
        ry, rz, re, rotx, roty = (0, 0, 0.003, 0, 0)
        flag_beam_divergence = False
        partiality_init, delta_xy_init, rs_init, rh_init = calc_partiality_anisotropy_set(
            crystal_init_orientation.unit_cell(),
            rotx,
            roty,
            observations.indices(),
            ry,
            rz,
            r0,
            re,
            two_theta,
            alpha_angle,
            wavelength,
            crystal_init_orientation,
            spot_pred_x_mm,
            spot_pred_y_mm,
            detector_distance_mm,
            "Lorentzian",
            flag_beam_divergence,
        )
        I_full = observations.data() / partiality_init
        sigI_full = observations.sigmas() / partiality_init
        observations_full = observations.customized_copy(data=I_full, sigmas=sigI_full)
        # calculate R and cc with reference
        cc_iso, cc_full_iso, cc_bin_low, cc_bin_med = (0, 0, 0, 0)
        observations_asu = observations.map_to_asu()
        observations_full_asu = observations_full.map_to_asu()
        cc_bins = flex.double()
        oodsqr_bins = flex.double()
        d_bins = flex.double()
        if flag_hklisoin_found:
            # build observations dict
            obs_dict = {}
            for mi_asu, I, sigI, I_full, sigI_full in zip(
                observations_asu.indices(),
                observations_asu.data(),
                observations_asu.sigmas(),
                observations_full_asu.data(),
                observations_full_asu.sigmas(),
            ):
                obs_dict[mi_asu] = (I, sigI, I_full, sigI_full)
            I_match = flex.double()
            I_full_match = flex.double()
            I_iso_match = flex.double()
            d_match = flex.double()
            oodsqr_match = flex.double()
            for mi_asu, d, I_iso in zip(
                miller_array_iso.indices(),
                miller_array_iso.d_spacings().data(),
                miller_array_iso.data(),
            ):
                if mi_asu in obs_dict:
                    I, sigI, I_full, sigI_full = obs_dict[mi_asu]
                    I_match.append(I)
                    I_full_match.append(I_full)
                    I_iso_match.append(I_iso)
                    oodsqr_match.append(1 / (d ** 2))
                    d_match.append(d)
            # calculate correlation
            cc_iso = np.corrcoef(I_iso_match, I_match)[0, 1]
            cc_full_iso = np.corrcoef(I_iso_match, I_full_match)[0, 1]
            # scatter plot
            if flag_plot and len(frame_files) == 1:
                plt.subplot(211)
                # plt.scatter(oodsqr_match, I_iso_match, s=10, marker='o', c='r')
                plt.plot(oodsqr_match, I_iso_match)
                plt.title("Reference intensity")
                plt.xlabel("1/d^2")
                plt.ylabel("I_ref")
                plt.subplot(212)
                # plt.scatter(oodsqr_match, I_match, s=10, marker='o', c='r')
                plt.plot(oodsqr_match, I_match)
                plt.title("Observed intensity CC=%.4g" % (cc_iso))
                plt.xlabel("1/d^2")
                plt.ylabel("I_obs")
                plt.show()
            # scatter bin plot
            n_bins = 10
            n_refl = int(round(len(I_match) / n_bins))
            if len(I_match) > 0:
                for i_bin in range(n_bins):
                    i_start = i_bin * n_refl
                    if i_bin < n_bins - 1:
                        i_end = (i_bin * n_refl) + n_refl
                    else:
                        i_end = -1
                    I_iso_bin = I_iso_match[i_start:i_end]
                    I_bin = I_match[i_start:i_end]
                    d_bin = d_match[i_start:i_end]
                    cc_bin = np.corrcoef(I_iso_bin, I_bin)[0, 1]
                    cc_bins.append(cc_bin)
                    try:
                        min_d_bin = np.min(d_bin)
                    except Exception:
                        min_d_bin = 1
                    d_bins.append(min_d_bin)
                    oodsqr_bins.append(1 / (min_d_bin ** 2))
                    if i_bin == 0:
                        cc_bin_low = cc_bin
                    if i_bin == 5:
                        cc_bin_med = cc_bin
                    if flag_plot and len(frame_files) == 1:
                        plt.subplot(2, 5, i_bin + 1)
                        plt.scatter(I_iso_bin, I_bin, s=10, marker="o", c="r")
                        plt.title(
                            "Bin %2.0f (%6.2f-%6.2f A) CC=%6.2f"
                            % (i_bin + 1, np.max(d_bin), np.min(d_bin), cc_bin)
                        )
                        if i_bin == 0:
                            plt.xlabel("I_ref")
                            plt.ylabel("I_obs")
                if flag_plot and len(frame_files) == 1:
                    plt.show()
            # print full detail if given a single file
            if len(frame_files) == 1:
                print "Crystal orientation"
                print crystal_init_orientation.crystal_rotation_matrix()
                print "Direct matrix"
                print crystal_init_orientation.direct_matrix()
        a, b, c, alpha, beta, gamma = observations.unit_cell().parameters()
        txt_out_head = "{0:80} {1:5.2f} {2:5.2f} {3:5.2f} {4:5.2f} {5:5.0f} {6:6.2f} {7:6.2f} {8:6.2f} {9:6.2f} {10:6.2f} {11:6.2f} {12:6.2f}".format(
            pickle_filename_only,
            observations.d_min(),
            np.max(observations.d_spacings().data()),
            xbeam,
            ybeam,
            len(observations.data()),
            cc_iso,
            np.mean(cc_bins),
            a,
            b,
            c,
            observations_pickle["mosaicity"],
            observations_pickle["residual"],
        )
        print txt_out_head
        cc_bin_low_set.append(cc_iso)
        cc_bins_set.append(cc_bins)
        d_bins_set.append(d_bins)
        oodsqr_bins_set.append(oodsqr_bins)
        sys_abs_lst = flex.double()
        if check_sys_absent:
            cn_refl = 0
            for sys_absent_flag, miller_index_ori, miller_index_asu, I, sigI in zip(
                observations.sys_absent_flags(),
                observations.indices(),
                observations_asu.indices(),
                observations.data(),
                observations.sigmas(),
            ):
                if sys_absent_flag[1]:
                    txt_out = " {0:3} {1:3} {2:3} {3:3} {4:3} {5:3} {6:8.2f} {7:8.2f} {8:6.2f}".format(
                        miller_index_ori[0],
                        miller_index_ori[1],
                        miller_index_ori[2],
                        miller_index_asu[0],
                        miller_index_asu[1],
                        miller_index_asu[2],
                        I,
                        sigI,
                        I / sigI,
                    )
                    if I / sigI > 3.0:
                        print txt_out
                    cn_refl += 1
                    sys_abs_lst.append(I / sigI)
                    sys_abs_all.append(I / sigI)
        sys_abs_set.append(sys_abs_lst)
    # collect beamxy
    xbeam_mean = flex.mean(xbeam_set)
    xbeam_std = np.std(xbeam_set)
    ybeam_mean = flex.mean(ybeam_set)
    ybeam_std = np.std(ybeam_set)
    xbeam_filtered_set = flex.double()
    ybeam_filtered_set = flex.double()
    frame_filtered_set = []
    sys_abs_all_filtered = flex.double()
    txt_out = ""
    txt_out_mix = ""
    txt_out_report_beam_filter = "Images with beam center displaced > %6.2f mm.:\n" % (
        beam_thres
    )
    txt_out_report_cc_filter = "Images with cc < %6.2f:\n" % (cc_bin_low_thres)
    from scitbx.matrix import col

    for pickle_filename, xbeam, ybeam, sys_abs_lst, cc_bin_low in zip(
        frame_files, xbeam_set, ybeam_set, sys_abs_set, cc_bin_low_set
    ):
        pickle_filename_arr = pickle_filename.split("/")
        pickle_filename_only = pickle_filename_arr[len(pickle_filename_arr) - 1]
        pred_xy = col((xbeam, ybeam))
        calc_xy = col((xbeam_mean, ybeam_mean))
        diff_xy = pred_xy - calc_xy
        txt_out_report_tmp = "{0:80} {1:6.2f} {2:6.2f} {3:6.2f} {4:6.4f}\n".format(
            pickle_filename_only, xbeam, ybeam, cc_bin_low, diff_xy.length()
        )
        if (
            abs(xbeam - xbeam_mean) / xbeam_std < 3.0
            and abs(ybeam - ybeam_mean) / ybeam_std < 3.0
        ):
            xbeam_filtered_set.append(xbeam)
            ybeam_filtered_set.append(ybeam)
            frame_filtered_set.append(pickle_filename)
            txt_out += pickle_filename + "\n"
            sys_abs_all_filtered.extend(sys_abs_lst)
            if cc_bin_low > cc_bin_low_thres:
                txt_out_mix += pickle_filename + "\n"
            else:
                txt_out_report_cc_filter += txt_out_report_tmp
        else:
            txt_out_report_beam_filter += txt_out_report_tmp
    print
    print "Xbeam mean=%8.4f std=%6.4f" % (xbeam_mean, xbeam_std)
    print "Ybeam mean=%8.4f std=%6.4f" % (ybeam_mean, ybeam_std)
    print "No. of frames: All = %6.0f Beam outliers = %6.0f CC filter=%6.0f" % (
        len(frame_files),
        len(frame_files) - (len(txt_out.split("\n")) - 1),
        len(frame_files) - (len(txt_out_mix.split("\n")) - 1),
    )
    print
    print "Reporting outliers (image name, xbeam, ybeam, cciso, delta_xy)"
    print txt_out_report_beam_filter
    print txt_out_report_cc_filter
    # write out filtered beamxy pickle files
    f = open("integration_pickle_beam_filter.lst", "w")
    f.write(txt_out)
    f.close()
    # write out mix filter pickle files
    f = open("integration_pickle_cc_filter.lst", "w")
    f.write(txt_out_mix)
    f.close()
    if flag_plot:
        plt.subplot(211)
        plt.plot(xbeam_set, ybeam_set, "r.")
        plt.xlim([xbeam_mean - 2, xbeam_mean + 2])
        plt.ylim([ybeam_mean - 2, ybeam_mean + 2])
        # plt.axes().set_aspect("equal")
        plt.title("Raw data")
        plt.grid(True)
        plt.subplot(212)
        plt.plot(xbeam_filtered_set, ybeam_filtered_set, "r.")
        plt.xlim([xbeam_mean - 2, xbeam_mean + 2])
        plt.ylim([ybeam_mean - 2, ybeam_mean + 2])
        # plt.axes().set_aspect("equal")
        plt.title("After beamxy position filter")
        plt.grid(True)
        plt.show()
        # plot I/sigI histogram for systematic absences
        if len(sys_abs_set) > 0:
            plt.subplot(211)
            x = sys_abs_all.as_numpy_array()
            mu = np.mean(x)
            med = np.median(x)
            sigma = np.std(x)
            num_bins = 20
            n, bins, patches = plt.hist(
                x, num_bins, normed=False, facecolor="green", alpha=0.5
            )
            # y = mlab.normpdf(bins, mu, sigma)
            # plt.plot(bins, y, 'r--')
            # plt.ylim([0,200])
            plt.ylabel("Frequencies")
            plt.title(
                "I/sigI distribution of systematic absences (Before BeamXY filter)\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(212)
            x = sys_abs_all_filtered.as_numpy_array()
            mu = np.mean(x)
            med = np.median(x)
            sigma = np.std(x)
            num_bins = 20
            n, bins, patches = plt.hist(
                x, num_bins, normed=False, facecolor="green", alpha=0.5
            )
            # y = mlab.normpdf(bins, mu, sigma)
            # plt.plot(bins, y, 'r--')
            # plt.ylim([0,200])
            plt.ylabel("Frequencies")
            plt.title(
                "I/sigI distribution of systematic absences (After BeamXY filter)\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.show()
        cn_i = 0
        for cc_bins, d_bins, oodsqrt_bins, cc_bin_low, pickle_filename in zip(
            cc_bins_set, d_bins_set, oodsqr_bins_set, cc_bin_low_set, frame_files
        ):
            pickle_filename_arr = pickle_filename.split("/")
            pickle_filename_only = pickle_filename_arr[len(pickle_filename_arr) - 1]
            if cc_bin_low < cc_bin_low_thres:
                plt.subplot(2, 1, 1)
                plt.plot(oodsqrt_bins, cc_bins)
                plt.title("CC by resolutions for cc < %6.2f" % (cc_bin_low_thres))
                plt.xlabel("1/d^2")
                plt.ylim([0, 1])
                plt.grid(True)
            else:
                plt.subplot(2, 1, 2)
                plt.plot(oodsqrt_bins, cc_bins)
                plt.title("CC by resolutions for cc > %6.2f" % (cc_bin_low_thres))
                plt.xlabel("1/d^2")
                plt.ylim([0, 1])
                plt.grid(True)
                cn_i += 1
        plt.show()
