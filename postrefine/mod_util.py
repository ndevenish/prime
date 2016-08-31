from __future__ import division
from scitbx.matrix import sqr
from cctbx.uctbx import unit_cell
from cctbx import miller
from cctbx import crystal
from cctbx.array_family import flex
from iotbx import mtz
from iotbx import reflection_file_reader
import math
import numpy as np
import matplotlib.pyplot as plt
from libtbx.utils import Sorry
from cctbx.uctbx import unit_cell


class intensities_scaler(object):
    """
    Author      : Uervirojnangkoorn, M.
    Created     : 7/13/2014
    Merge equivalent reflections and report intensity and refinement statistics.
    """

    def __init__(self):
        """Constructor."""
        self.CONST_SE_MIN_WEIGHT = 0.17
        self.CONST_SE_MAX_WEIGHT = 1.0
        self.CONST_SIG_I_FACTOR = 1.5

    def calculate_SE(self, results, iparams):
        """Take all post-refinement results, calculate covariances and new
        SE."""
        if results[0].grad_set is None:
            return results
        else:
            # get miller array iso for comparison, if given
            mxh = mx_handler()
            flag_hklisoin_found, miller_array_iso = mxh.get_miller_array_from_reflection_file(
                iparams.hklisoin
            )
            # get reference set
            import os

            fileseq_list = flex.int()
            for file_in in os.listdir(iparams.run_no):
                if file_in.endswith(".mtz"):
                    file_split = file_in.split("_")
                    if len(file_split) > 3:
                        fileseq_list.append(int(file_split[2]))
            if len(fileseq_list) == 0:
                hklref = "mean_scaled_merge.mtz"
            else:
                hklref = "postref_cycle_" + str(flex.max(fileseq_list)) + "_merge.mtz"
            flag_hklref_found, miller_array_ref = mxh.get_miller_array_from_reflection_file(
                iparams.run_no + "/" + hklref
            )
            # calculate covariance
            X = np.array(
                [
                    [
                        pres.G,
                        pres.B,
                        pres.tau,
                        pres.rotx,
                        pres.roty,
                        pres.ry,
                        pres.rz,
                        pres.r0,
                        pres.re,
                        pres.uc_params[0],
                        pres.uc_params[1],
                        pres.uc_params[2],
                        pres.uc_params[3],
                        pres.uc_params[4],
                        pres.uc_params[5],
                    ]
                    for pres in results
                ]
            ).T
            COV = np.cov(X)
            COV_diag = flex.double([i for i in COV.diagonal()])
            # calculate standard errors
            output_results = []
            for pres in results:
                sigI = pres.observations.sigmas()
                observations_old = pres.observations.deep_copy()
                var_set = (pres.grad_set ** 2) * COV_diag
                sin_theta_over_lambda_sq = (
                    pres.observations.two_theta(wavelength=pres.wavelength)
                    .sin_theta_over_lambda_sq()
                    .data()
                )
                d_spacings = pres.observations.d_spacings().data()
                scale_factors_by_indices = pres.G * flex.exp(
                    -2 * pres.B * sin_theta_over_lambda_sq
                )
                var_scale_factors = var_set[0] + var_set[1]
                var_partiality = flex.sum(var_set[3:])
                err_scale_factors = var_scale_factors / (scale_factors_by_indices ** 2)
                err_partiality = var_partiality / (pres.partiality ** 2)
                err_tau = var_set[2] / ((pres.tau ** 2) + 1e-9)
                # determine weight
                I_o_full = (
                    (4 * pres.rs_set * pres.observations.data())
                    / (
                        3
                        * pres.e_width_set
                        * scale_factors_by_indices
                        * pres.partiality
                    )
                ) + pres.tau
                observations_full = pres.observations.customized_copy(data=I_o_full)
                observations_err_scale = pres.observations.customized_copy(
                    data=err_scale_factors
                )
                observations_err_p = pres.observations.customized_copy(
                    data=err_partiality
                )
                observations_err_tau = pres.observations.customized_copy(
                    data=flex.double([err_tau] * len(pres.observations.data()))
                )
                flag_reset_weight = False
                if flag_hklref_found:
                    ma_ref, ma_obs_full = miller_array_ref.common_sets(
                        observations_full, assert_is_similar_symmetry=False
                    )
                    dummy, ma_err_scale = miller_array_ref.common_sets(
                        observations_err_scale, assert_is_similar_symmetry=False
                    )
                    dummy, ma_err_p = miller_array_ref.common_sets(
                        observations_err_p, assert_is_similar_symmetry=False
                    )
                    dummy, ma_err_tau = miller_array_ref.common_sets(
                        observations_err_tau, assert_is_similar_symmetry=False
                    )
                    r1_factor = ma_ref.data() - ma_obs_full.data()
                    SE_I_WEIGHT = max(
                        [
                            flex.linear_correlation(
                                (ma_obs_full.sigmas() ** 2), flex.log(r1_factor ** 2)
                            ).coefficient(),
                            0,
                        ]
                    )
                    SE_SCALE_WEIGHT = max(
                        [
                            flex.linear_correlation(
                                ma_err_scale.data(), flex.log(r1_factor ** 2)
                            ).coefficient(),
                            0,
                        ]
                    )
                    SE_EOC_WEIGHT = max(
                        [
                            flex.linear_correlation(
                                ma_err_p.data(), flex.log(r1_factor ** 2)
                            ).coefficient(),
                            0,
                        ]
                    )
                    SE_TAU_WEIGHT = max(
                        [
                            flex.linear_correlation(
                                ma_err_tau.data(), flex.log(r1_factor ** 2)
                            ).coefficient(),
                            0,
                        ]
                    )
                else:
                    flag_reset_weight = True
                if True:
                    SE_I_WEIGHT = self.CONST_SE_I_WEIGHT
                    SE_SCALE_WEIGHT = self.CONST_SE_SCALE_WEIGHT
                    SE_EOC_WEIGHT = self.CONST_SE_EOC_WEIGHT
                    SE_TAU_WEIGHT = self.CONST_SE_TAU_WEIGHT
                # calculate new sigma
                new_sigI = flex.sqrt(
                    (SE_I_WEIGHT * (sigI ** 2))
                    + (
                        SE_SCALE_WEIGHT
                        * (
                            err_scale_factors
                            * (
                                flex.sum(sigI ** 2)
                                / (flex.sum(err_scale_factors) + 1e-9)
                            )
                        )
                    )
                    + (
                        SE_TAU_WEIGHT
                        * (
                            err_tau
                            * (flex.sum(sigI ** 2) / ((err_tau * len(sigI)) + 1e-9))
                        )
                    )
                    + (
                        SE_EOC_WEIGHT
                        * (
                            err_partiality
                            * (flex.sum(sigI ** 2) / (flex.sum(err_partiality) + 1e-9))
                        )
                    )
                )
                # for i in new_sigI:
                #  if math.isnan(i) or i == float('inf') or i<0.1:
                #    print i, SE_I_WEIGHT, SE_SCALE_WEIGHT, SE_EOC_WEIGHT, SE_TAU_WEIGHT
                pres.set_params(
                    observations=pres.observations.customized_copy(sigmas=new_sigI),
                    observations_original=pres.observations_original.customized_copy(
                        sigmas=new_sigI
                    ),
                )
                output_results.append(pres)
                # for plotting
                if iparams.flag_plot_expert:
                    plt.subplot(521)
                    plt.scatter(
                        1 / (d_spacings ** 2),
                        scale_factors_by_indices,
                        s=10,
                        marker="x",
                        c="r",
                    )
                    plt.title("Scale factors")
                    plt.subplot(522)
                    plt.scatter(
                        1 / (d_spacings ** 2), pres.partiality, s=10, marker="x", c="r"
                    )
                    plt.title("Partiality")
                    plt.subplot(523)
                    plt.scatter(
                        1 / (d_spacings ** 2),
                        err_scale_factors,
                        s=10,
                        marker="x",
                        c="r",
                    )
                    plt.title("Error in scale factors")
                    plt.subplot(524)
                    plt.scatter(
                        1 / (d_spacings ** 2), err_partiality, s=10, marker="x", c="r"
                    )
                    plt.title("Error in partiality")
                    plt.subplot(525)
                    plt.scatter(1 / (d_spacings ** 2), sigI, s=10, marker="x", c="r")
                    plt.title("Original sigmas")
                    plt.subplot(526)
                    plt.scatter(
                        1 / (d_spacings ** 2), new_sigI, s=10, marker="x", c="r"
                    )
                    plt.title("New sigmas")
                    plt.subplot(527)
                    plt.scatter(
                        1 / (d_spacings ** 2),
                        flex.log(pres.observations.data()),
                        s=10,
                        marker="x",
                        c="r",
                    )
                    plt.title("Original I")
                    plt.subplot(528)
                    plt.scatter(
                        1 / (d_spacings ** 2),
                        flex.log(observations_full.data()),
                        s=10,
                        marker="x",
                        c="r",
                    )
                    plt.title("New I")
                    if miller_array_iso is not None:
                        ma_iso, ma_obs_old = miller_array_iso.common_sets(
                            observations_old, assert_is_similar_symmetry=False
                        )
                        ma_iso, ma_obs_full = miller_array_iso.common_sets(
                            observations_full, assert_is_similar_symmetry=False
                        )
                        plt.subplot(529)
                        plt.scatter(
                            ma_obs_old.sigmas(),
                            flex.log(flex.abs(ma_iso.data() - ma_obs_old.data())),
                            s=10,
                            marker="x",
                            c="r",
                        )
                        plt.title(
                            "Original SE vs Log Residual (R=%6.1f CC=%6.2f)"
                            % (
                                flex.sum(flex.abs(ma_iso.data() - ma_obs_old.data()))
                                / flex.sum(flex.abs(ma_obs_old.data())),
                                flex.linear_correlation(
                                    ma_obs_old.sigmas(),
                                    flex.log(
                                        flex.abs(ma_iso.data() - ma_obs_old.data())
                                    ),
                                ).coefficient(),
                            )
                        )
                        plt.subplot(5, 2, 10)
                        plt.scatter(
                            ma_obs_full.sigmas(),
                            flex.log(flex.abs(ma_iso.data() - ma_obs_full.data())),
                            s=10,
                            marker="x",
                            c="r",
                        )
                        plt.title(
                            "New SE vs Log Residual (R=%6.1f CC=%6.2f)"
                            % (
                                flex.sum(flex.abs(ma_iso.data() - ma_obs_full.data()))
                                / flex.sum(flex.abs(ma_obs_full.data())),
                                flex.linear_correlation(
                                    ma_obs_full.sigmas(),
                                    flex.log(
                                        flex.abs(ma_iso.data() - ma_obs_full.data())
                                    ),
                                ).coefficient(),
                            )
                        )
                    plt.show()
            return output_results

    def calc_avg_I_cpp(
        self,
        group_no,
        group_id_list,
        miller_index,
        miller_indices_ori,
        I,
        sigI,
        G,
        B,
        p_set,
        rs_set,
        wavelength_set,
        sin_theta_over_lambda_sq,
        SE,
        avg_mode,
        iparams,
        pickle_filename_set,
    ):
        from prime import Average_Mode, averaging_engine

        if avg_mode == "average":
            avg_mode_cpp = Average_Mode.Average
        elif avg_mode == "weighted":
            avg_mode_cpp = Average_Mode.Weighted
        elif avg_mode == "final":
            avg_mode_cpp = Average_Mode.Final
        else:
            raise Sorry("Bad averaging mode selected: %s" % avg_mode)
        sigma_max = iparams.sigma_rejection
        engine = averaging_engine(
            group_no,
            group_id_list,
            miller_index,
            miller_indices_ori,
            I,
            sigI,
            G,
            B,
            p_set,
            rs_set,
            wavelength_set,
            sin_theta_over_lambda_sq,
            SE,
            pickle_filename_set,
        )
        engine.avg_mode = avg_mode_cpp
        engine.sigma_max = sigma_max
        engine.flag_volume_correction = False
        engine.n_rejection_cycle = iparams.n_rejection_cycle
        engine.flag_output_verbose = iparams.flag_output_verbose
        results = engine.calc_avg_I()
        return (
            results.miller_index,
            results.I_avg,
            results.sigI_avg,
            (
                results.r_meas_w_top,
                results.r_meas_w_btm,
                results.r_meas_top,
                results.r_meas_btm,
                results.multiplicity,
            ),
            (
                results.I_avg_even,
                results.I_avg_odd,
                results.I_avg_even_h,
                results.I_avg_odd_h,
                results.I_avg_even_k,
                results.I_avg_odd_k,
                results.I_avg_even_l,
                results.I_avg_odd_l,
            ),
            results.txt_obs_out,
            results.txt_reject_out,
        )

    def calc_mean_unit_cell(self, results):
        a_all = flex.double()
        b_all = flex.double()
        c_all = flex.double()
        alpha_all = flex.double()
        beta_all = flex.double()
        gamma_all = flex.double()
        for pres in results:
            if pres is not None:
                a_all.append(pres.uc_params[0])
                b_all.append(pres.uc_params[1])
                c_all.append(pres.uc_params[2])
                alpha_all.append(pres.uc_params[3])
                beta_all.append(pres.uc_params[4])
                gamma_all.append(pres.uc_params[5])
        uc_mean = flex.double(
            [
                np.mean(a_all),
                np.mean(b_all),
                np.mean(c_all),
                np.mean(alpha_all),
                np.mean(beta_all),
                np.mean(gamma_all),
            ]
        )
        uc_med = flex.double(
            [
                np.median(a_all),
                np.median(b_all),
                np.median(c_all),
                np.median(alpha_all),
                np.median(beta_all),
                np.median(gamma_all),
            ]
        )
        uc_std = flex.double(
            [
                np.std(a_all),
                np.std(b_all),
                np.std(c_all),
                np.std(alpha_all),
                np.std(beta_all),
                np.std(gamma_all),
            ]
        )
        return uc_mean, uc_med, uc_std

    def calc_mean_postref_parameters(self, results):
        G_all = flex.double()
        B_all = flex.double()
        rotx_all = flex.double()
        roty_all = flex.double()
        ry_all = flex.double()
        rz_all = flex.double()
        re_all = flex.double()
        r0_all = flex.double()
        voigt_nu_all = flex.double()
        R_final_all = flex.double()
        R_xy_final_all = flex.double()
        SE_all = flex.double()
        for pres in results:
            if pres is not None:
                if not math.isnan(pres.G):
                    G_all.append(pres.G)
                if not math.isnan(pres.B):
                    B_all.append(pres.B)
                if not math.isnan(pres.rotx):
                    rotx_all.append(pres.rotx)
                if not math.isnan(pres.roty):
                    roty_all.append(pres.roty)
                if not math.isnan(pres.ry):
                    ry_all.append(pres.ry)
                if not math.isnan(pres.rz):
                    rz_all.append(pres.rz)
                if not math.isnan(pres.re):
                    re_all.append(pres.re)
                if not math.isnan(pres.r0):
                    r0_all.append(pres.r0)
                if not math.isnan(pres.voigt_nu):
                    voigt_nu_all.append(pres.voigt_nu)
                if not math.isnan(pres.R_final):
                    R_final_all.append(pres.R_final)
                if not math.isnan(pres.R_xy_final):
                    R_xy_final_all.append(pres.R_xy_final)
                if not math.isnan(pres.SE):
                    SE_all.append(pres.SE)

        pr_params_mean = flex.double(
            [
                np.mean(G_all),
                np.mean(B_all),
                np.mean(flex.abs(ry_all)),
                np.mean(flex.abs(rz_all)),
                np.mean(flex.abs(re_all)),
                np.mean(flex.abs(r0_all)),
                np.mean(flex.abs(voigt_nu_all)),
                np.mean(flex.abs(rotx_all)),
                np.mean(flex.abs(roty_all)),
                np.mean(R_final_all),
                np.mean(R_xy_final_all),
                np.mean(SE_all),
            ]
        )
        pr_params_med = flex.double(
            [
                np.median(G_all),
                np.median(B_all),
                np.median(flex.abs(ry_all)),
                np.median(flex.abs(rz_all)),
                np.median(flex.abs(re_all)),
                np.median(flex.abs(r0_all)),
                np.median(flex.abs(voigt_nu_all)),
                np.median(flex.abs(rotx_all)),
                np.median(flex.abs(roty_all)),
                np.median(R_final_all),
                np.median(R_xy_final_all),
                np.median(SE_all),
            ]
        )
        pr_params_std = flex.double(
            [
                np.std(G_all),
                np.std(B_all),
                np.std(flex.abs(ry_all)),
                np.std(flex.abs(rz_all)),
                np.std(flex.abs(re_all)),
                np.std(flex.abs(r0_all)),
                np.std(flex.abs(voigt_nu_all)),
                np.std(flex.abs(rotx_all)),
                np.std(flex.abs(roty_all)),
                np.std(R_final_all),
                np.std(R_xy_final_all),
                np.std(SE_all),
            ]
        )

        return pr_params_mean, pr_params_med, pr_params_std

    def prepare_output(self, results, iparams, avg_mode):
        if avg_mode == "average":
            cc_thres = 0
        else:
            cc_thres = iparams.frame_accept_min_cc
        std_filter = iparams.sigma_rejection
        if iparams.flag_weak_anomalous:
            if avg_mode == "final":
                target_anomalous_flag = iparams.target_anomalous_flag
            else:
                target_anomalous_flag = False
        else:
            target_anomalous_flag = iparams.target_anomalous_flag
        pr_params_mean, pr_params_med, pr_params_std = self.calc_mean_postref_parameters(
            results
        )
        G_mean, B_mean, ry_mean, rz_mean, re_mean, r0_mean, voigt_nu_mean, rotx_mean, roty_mean, R_mean, R_xy_mean, SE_mean = (
            pr_params_mean
        )
        G_med, B_med, ry_med, rz_med, re_med, r0_med, voigt_nu_med, rotx_med, roty_med, R_med, R_xy_med, SE_med = (
            pr_params_med
        )
        G_std, B_std, ry_std, rz_std, re_std, r0_std, voigt_nu_std, rotx_std, roty_std, R_std, R_xy_std, SE_std = (
            pr_params_std
        )
        # prepare data for merging
        miller_indices_all = flex.miller_index()
        miller_indices_ori_all = flex.miller_index()
        I_all = flex.double()
        sigI_all = flex.double()
        G_all = flex.double()
        B_all = flex.double()
        p_all = flex.double()
        rx_all = flex.double()
        rs_all = flex.double()
        rh_all = flex.double()
        SE_all = flex.double()
        sin_sq_all = flex.double()
        wavelength_all = flex.double()
        detector_distance_set = flex.double()
        R_init_all = flex.double()
        R_final_all = flex.double()
        R_xy_init_all = flex.double()
        R_xy_final_all = flex.double()
        pickle_filename_all = []
        filtered_results = []
        cn_good_frame, cn_bad_frame_SE, cn_bad_frame_uc, cn_bad_frame_cc, cn_bad_frame_G, cn_bad_frame_re = (
            0,
            0,
            0,
            0,
            0,
            0,
        )
        i_seq = flex.int()
        crystal_orientation_dict = {}
        for pres in results:
            if pres is not None:
                pickle_filepath = pres.pickle_filename.split("/")
                img_filename = pickle_filepath[len(pickle_filepath) - 1]
                flag_pres_ok = True
                # check SE, CC, UC, G, B, gamma_e
                if math.isnan(pres.G):
                    flag_pres_ok = False
                if math.isnan(pres.SE) or np.isinf(pres.SE):
                    flag_pres_ok = False
                if flag_pres_ok and SE_std > 0:
                    if abs(pres.SE - SE_med) / SE_std > std_filter:
                        flag_pres_ok = False
                        cn_bad_frame_SE += 1
                if flag_pres_ok and pres.CC_final < cc_thres:
                    flag_pres_ok = False
                    cn_bad_frame_cc += 1
                if flag_pres_ok:
                    if G_std > 0:
                        if abs(pres.G - G_med) / G_std > std_filter:
                            flag_pres_ok = False
                            cn_bad_frame_G += 1
                if flag_pres_ok:
                    if re_std > 0:
                        if abs(pres.re - re_med) / (math.sqrt(re_med)) > std_filter:
                            flag_pres_ok = False
                            cn_bad_frame_re += 1
                from mod_leastsqr import good_unit_cell

                if flag_pres_ok and not good_unit_cell(
                    pres.uc_params, iparams, iparams.merge.uc_tolerance
                ):
                    flag_pres_ok = False
                    cn_bad_frame_uc += 1
                if flag_pres_ok:
                    cn_good_frame += 1
                    sin_theta_over_lambda_sq = (
                        pres.observations.two_theta(wavelength=pres.wavelength)
                        .sin_theta_over_lambda_sq()
                        .data()
                    )
                    filtered_results.append(pres)
                    R_init_all.append(pres.R_init)
                    R_final_all.append(pres.R_final)
                    R_xy_init_all.append(pres.R_xy_init)
                    R_xy_final_all.append(pres.R_xy_final)
                    miller_indices_all.extend(pres.observations.indices())
                    miller_indices_ori_all.extend(pres.observations_original.indices())
                    I_all.extend(pres.observations.data())
                    sigI_all.extend(pres.observations.sigmas())
                    G_all.extend(flex.double([pres.G] * len(pres.observations.data())))
                    B_all.extend(flex.double([pres.B] * len(pres.observations.data())))
                    p_all.extend(pres.partiality)
                    rs_all.extend(pres.rs_set)
                    rh_all.extend(pres.rh_set)
                    sin_sq_all.extend(sin_theta_over_lambda_sq)
                    SE_all.extend(
                        flex.double([pres.SE] * len(pres.observations.data()))
                    )
                    wavelength_all.extend(
                        flex.double([pres.wavelength] * len(pres.observations.data()))
                    )
                    detector_distance_set.append(pres.detector_distance_mm)
                    pickle_filename_all += [
                        pres.pickle_filename
                        for i in range(len(pres.observations.data()))
                    ]
                    i_seq.extend(
                        flex.int(
                            [
                                i
                                for i in range(
                                    len(i_seq),
                                    len(i_seq) + len(pres.observations.data()),
                                )
                            ]
                        )
                    )
                    crystal_orientation_dict[
                        pres.pickle_filename
                    ] = pres.crystal_orientation
        # plot stats
        self.plot_stats(filtered_results, iparams)
        # write out updated crystal orientation as a pickle file
        import cPickle as pickle

        pickle.dump(
            crystal_orientation_dict,
            open(iparams.run_no + "/" + "crystal.o", "wb"),
            pickle.HIGHEST_PROTOCOL,
        )
        # calculate average unit cell
        uc_mean, uc_med, uc_std = self.calc_mean_unit_cell(filtered_results)
        unit_cell_mean = unit_cell(
            (uc_mean[0], uc_mean[1], uc_mean[2], uc_mean[3], uc_mean[4], uc_mean[5])
        )
        # recalculate stats for pr parameters
        pr_params_mean, pr_params_med, pr_params_std = self.calc_mean_postref_parameters(
            filtered_results
        )
        G_mean, B_mean, ry_mean, rz_mean, re_mean, r0_mean, voigt_nu_mean, rotx_mean, roty_mean, R_mean, R_xy_mean, SE_mean = (
            pr_params_mean
        )
        G_med, B_med, ry_med, rz_med, re_med, r0_med, voigt_nu_med, rotx_med, roty_med, R_med, R_xy_med, SE_med = (
            pr_params_med
        )
        G_std, B_std, ry_std, rz_std, re_std, r0_std, voigt_nu_std, rotx_std, roty_std, R_std, R_xy_std, SE_std = (
            pr_params_std
        )
        # from all observations merge them
        crystal_symmetry = crystal.symmetry(
            unit_cell=(
                uc_mean[0],
                uc_mean[1],
                uc_mean[2],
                uc_mean[3],
                uc_mean[4],
                uc_mean[5],
            ),
            space_group_symbol=iparams.target_space_group,
        )
        miller_set_all = miller.set(
            crystal_symmetry=crystal_symmetry,
            indices=miller_indices_all,
            anomalous_flag=target_anomalous_flag,
        )
        miller_array_all = miller_set_all.array(
            data=I_all, sigmas=sigI_all
        ).set_observation_type_xray_intensity()
        # sort reflections according to asymmetric-unit symmetry hkl
        perm = miller_array_all.sort_permutation(by_value="packed_indices")
        miller_indices_all_sort = miller_array_all.indices().select(perm)
        miller_indices_ori_all_sort = miller_indices_ori_all.select(perm)
        I_obs_all_sort = miller_array_all.data().select(perm)
        sigI_obs_all_sort = miller_array_all.sigmas().select(perm)
        G_all_sort = G_all.select(perm)
        B_all_sort = B_all.select(perm)
        p_all_sort = p_all.select(perm)
        rs_all_sort = rs_all.select(perm)
        wavelength_all_sort = wavelength_all.select(perm)
        sin_sq_all_sort = sin_sq_all.select(perm)
        SE_all_sort = SE_all.select(perm)
        i_seq_sort = i_seq.select(perm)
        pickle_filename_all_sort = [pickle_filename_all[i] for i in i_seq_sort]
        miller_array_uniq = (
            miller_array_all.merge_equivalents()
            .array()
            .complete_array(d_min=iparams.merge.d_min, d_max=iparams.merge.d_max)
        )
        matches_uniq = miller.match_multi_indices(
            miller_indices_unique=miller_array_uniq.indices(),
            miller_indices=miller_indices_all_sort,
        )
        pair_0 = flex.int([pair[0] for pair in matches_uniq.pairs()])
        pair_1 = flex.int([pair[1] for pair in matches_uniq.pairs()])
        group_id_list = flex.int(
            [pair_0[pair_1[i]] for i in range(len(matches_uniq.pairs()))]
        )
        from collections import Counter

        tally = Counter()
        for elem in group_id_list:
            tally[elem] += 1
        cn_group = len(tally)
        # preparte txt out stat
        txt_out = "Summary of refinement and merging\n"
        txt_out += " No. good frames:          %12.0f\n" % (cn_good_frame)
        txt_out += " No. bad cc frames:        %12.0f\n" % (cn_bad_frame_cc)
        txt_out += " No. bad G frames) :       %12.0f\n" % (cn_bad_frame_G)
        txt_out += " No. bad unit cell frames: %12.0f\n" % (cn_bad_frame_uc)
        txt_out += " No. bad gamma_e frames:   %12.0f\n" % (cn_bad_frame_re)
        txt_out += " No. bad SE:               %12.0f\n" % (cn_bad_frame_SE)
        txt_out += " No. observations:         %12.0f\n" % (len(I_obs_all_sort))
        txt_out += "Mean target value (BEFORE: Mean Median (Std.))\n"
        txt_out += " post-refinement:          %12.2f %12.2f (%9.2f)\n" % (
            np.mean(R_init_all),
            np.median(R_init_all),
            np.std(R_init_all),
        )
        txt_out += " (x,y) restraints:         %12.2f %12.2f (%9.2f)\n" % (
            np.mean(R_xy_init_all),
            np.median(R_xy_init_all),
            np.std(R_xy_init_all),
        )
        txt_out += "Mean target value (AFTER: Mean Median (Std.))\n"
        txt_out += " post-refinement:          %12.2f %12.2f (%9.2f)\n" % (
            np.mean(R_final_all),
            np.median(R_final_all),
            np.std(R_final_all),
        )
        txt_out += " (x,y) restraints:         %12.2f %12.2f (%9.2f)\n" % (
            np.mean(R_xy_final_all),
            np.median(R_xy_final_all),
            np.std(R_xy_final_all),
        )
        txt_out += " SE:                       %12.2f %12.2f (%9.2f)\n" % (
            SE_mean,
            SE_med,
            SE_std,
        )
        txt_out += " G:                        %12.3e %12.3e (%9.2e)\n" % (
            G_mean,
            G_med,
            G_std,
        )
        txt_out += " B:                        %12.2f %12.2f (%9.2f)\n" % (
            B_mean,
            B_med,
            B_std,
        )
        txt_out += " Rot.x:                    %12.2f %12.2f (%9.2f)\n" % (
            rotx_mean * 180 / math.pi,
            rotx_med * 180 / math.pi,
            rotx_std * 180 / math.pi,
        )
        txt_out += " Rot.y:                    %12.2f %12.2f (%9.2f)\n" % (
            roty_mean * 180 / math.pi,
            roty_med * 180 / math.pi,
            roty_std * 180 / math.pi,
        )
        txt_out += " gamma_y:                  %12.5f %12.5f (%9.5f)\n" % (
            ry_mean,
            ry_med,
            ry_std,
        )
        txt_out += " gamma_z:                  %12.5f %12.5f (%9.5f)\n" % (
            rz_mean,
            rz_med,
            rz_std,
        )
        txt_out += " gamma_0:                  %12.5f %12.5f (%9.5f)\n" % (
            r0_mean,
            r0_med,
            r0_std,
        )
        txt_out += " gamma_e:                  %12.5f %12.5f (%9.5f)\n" % (
            re_mean,
            re_med,
            re_std,
        )
        txt_out += " voigt_nu:                 %12.5f %12.5f (%9.5f)\n" % (
            voigt_nu_mean,
            voigt_nu_med,
            voigt_nu_std,
        )
        txt_out += " unit cell\n"
        txt_out += "   a:                      %12.2f %12.2f (%9.2f)\n" % (
            uc_mean[0],
            uc_med[0],
            uc_std[0],
        )
        txt_out += "   b:                      %12.2f %12.2f (%9.2f)\n" % (
            uc_mean[1],
            uc_med[1],
            uc_std[1],
        )
        txt_out += "   c:                      %12.2f %12.2f (%9.2f)\n" % (
            uc_mean[2],
            uc_med[2],
            uc_std[2],
        )
        txt_out += "   alpha:                  %12.2f %12.2f (%9.2f)\n" % (
            uc_mean[3],
            uc_med[3],
            uc_std[3],
        )
        txt_out += "   beta:                   %12.2f %12.2f (%9.2f)\n" % (
            uc_mean[4],
            uc_med[4],
            uc_std[4],
        )
        txt_out += "   gamma:                  %12.2f %12.2f (%9.2f)\n" % (
            uc_mean[5],
            uc_med[5],
            uc_std[5],
        )
        txt_out += "Parmeters from integration (not-refined)\n"
        txt_out += "  Wavelength:              %12.5f %12.5f (%9.5f)\n" % (
            np.mean(wavelength_all),
            np.median(wavelength_all),
            np.std(wavelength_all),
        )
        txt_out += "  Detector distance:       %12.5f %12.5f (%9.5f)\n" % (
            np.mean(detector_distance_set),
            np.median(detector_distance_set),
            np.std(detector_distance_set),
        )
        txt_out += "* (standard deviation)\n"
        # write out stat. pickle
        stat_dict = {
            "n_frames_good": [cn_good_frame],
            "n_frames_bad_cc": [cn_bad_frame_cc],
            "n_frames_bad_G": [cn_bad_frame_G],
            "n_frames_bad_uc": [cn_bad_frame_uc],
            "n_frames_bad_gamma_e": [cn_bad_frame_re],
            "n_frames_bad_SE": [cn_bad_frame_SE],
            "n_observations": [len(I_obs_all_sort)],
            "R_start": [np.mean(R_init_all)],
            "R_end": [np.mean(R_final_all)],
            "R_xy_start": [np.mean(R_xy_init_all)],
            "R_xy_end": [np.mean(R_xy_final_all)],
            "mean_gamma_y": [ry_mean],
            "std_gamma_y": [ry_std],
            "mean_gamma_z": [rz_mean],
            "std_gamma_z": [rz_std],
            "mean_gamma_0": [r0_mean],
            "std_gamma_0": [r0_std],
            "mean_gamma_e": [re_mean],
            "std_gamma_e": [re_std],
            "mean_voigt_nu": [voigt_nu_mean],
            "std_voigt_nu": [voigt_nu_std],
            "mean_a": [uc_mean[0]],
            "std_a": [uc_std[0]],
            "mean_b": [uc_mean[1]],
            "std_b": [uc_std[1]],
            "mean_c": [uc_mean[2]],
            "std_c": [uc_std[2]],
            "mean_alpha": [uc_mean[3]],
            "std_alpha": [uc_std[3]],
            "mean_beta": [uc_mean[4]],
            "std_beta": [uc_std[4]],
            "mean_gamma": [uc_mean[5]],
            "std_gamma": [uc_std[5]],
        }
        psh = pickle_stat_handler()
        psh.write_pickle(iparams, stat_dict)
        return (
            cn_group,
            group_id_list,
            miller_indices_all_sort,
            miller_indices_ori_all_sort,
            I_obs_all_sort,
            sigI_obs_all_sort,
            G_all_sort,
            B_all_sort,
            p_all_sort,
            rs_all_sort,
            wavelength_all_sort,
            sin_sq_all_sort,
            SE_all_sort,
            uc_mean,
            np.mean(wavelength_all),
            pickle_filename_all_sort,
            txt_out,
        )

    def params_selection(
        self,
        selections,
        miller_array_merge,
        I_even,
        I_odd,
        I_even_h,
        I_odd_h,
        I_even_k,
        I_odd_k,
        I_even_l,
        I_odd_l,
        r_meas_w_top,
        r_meas_w_btm,
        r_meas_top,
        r_meas_btm,
        multiplicity,
    ):
        # perform selection
        miller_array_merge = miller_array_merge.select(selections)
        I_even = I_even.select(selections)
        I_odd = I_odd.select(selections)
        I_even_h = I_even_h.select(selections)
        I_odd_h = I_odd_h.select(selections)
        I_even_k = I_even_k.select(selections)
        I_odd_k = I_odd_k.select(selections)
        I_even_l = I_even_l.select(selections)
        I_odd_l = I_odd_l.select(selections)
        r_meas_w_top = r_meas_w_top.select(selections)
        r_meas_w_btm = r_meas_w_btm.select(selections)
        r_meas_top = r_meas_top.select(selections)
        r_meas_btm = r_meas_btm.select(selections)
        multiplicity = multiplicity.select(selections)
        return (
            miller_array_merge,
            I_even,
            I_odd,
            I_even_h,
            I_odd_h,
            I_even_k,
            I_odd_k,
            I_even_l,
            I_odd_l,
            r_meas_w_top,
            r_meas_w_btm,
            r_meas_top,
            r_meas_btm,
            multiplicity,
        )

    def write_output(
        self,
        miller_indices_merge,
        I_merge,
        sigI_merge,
        stat_all,
        I_two_halves_tuple,
        iparams,
        uc_mean,
        wavelength_mean,
        output_mtz_file_prefix,
        avg_mode,
    ):
        if iparams.flag_weak_anomalous:
            if avg_mode == "final":
                target_anomalous_flag = iparams.target_anomalous_flag
            else:
                target_anomalous_flag = False
        else:
            target_anomalous_flag = iparams.target_anomalous_flag
        # extract stats, I_even and I_odd pair
        r_meas_w_top, r_meas_w_btm, r_meas_top, r_meas_btm, multiplicity = stat_all
        I_even, I_odd, I_even_h, I_odd_h, I_even_k, I_odd_k, I_even_l, I_odd_l = (
            I_two_halves_tuple
        )
        # output mtz file and report binning stat
        miller_set_merge = crystal.symmetry(
            unit_cell=unit_cell(
                (uc_mean[0], uc_mean[1], uc_mean[2], uc_mean[3], uc_mean[4], uc_mean[5])
            ),
            space_group_symbol=iparams.target_space_group,
        ).build_miller_set(
            anomalous_flag=target_anomalous_flag, d_min=iparams.merge.d_min
        )
        miller_array_merge = (
            miller_set_merge.array()
            .customized_copy(
                indices=miller_indices_merge,
                data=I_merge,
                sigmas=sigI_merge,
                anomalous_flag=target_anomalous_flag,
            )
            .map_to_asu()
            .set_observation_type_xray_intensity()
        )
        miller_array_complete = miller_set_merge.array()
        fake_data = flex.double([1.0] * len(miller_array_complete.indices()))
        miller_array_template_asu = miller_array_complete.customized_copy(
            data=fake_data, sigmas=fake_data
        ).resolution_filter(d_min=iparams.merge.d_min, d_max=iparams.merge.d_max)
        n_refl_all = len(miller_array_merge.data())
        # do another resolution filter here
        i_sel_res = miller_array_merge.resolution_filter_selection(
            d_min=iparams.merge.d_min, d_max=iparams.merge.d_max
        )
        miller_array_merge, I_even, I_odd, I_even_h, I_odd_h, I_even_k, I_odd_k, I_even_l, I_odd_l, r_meas_w_top, r_meas_w_btm, r_meas_top, r_meas_btm, multiplicity = self.params_selection(
            i_sel_res,
            miller_array_merge,
            I_even,
            I_odd,
            I_even_h,
            I_odd_h,
            I_even_k,
            I_odd_k,
            I_even_l,
            I_odd_l,
            r_meas_w_top,
            r_meas_w_btm,
            r_meas_top,
            r_meas_btm,
            multiplicity,
        )
        n_refl_out_resolutions = n_refl_all - len(miller_array_merge.data())
        # remove outliers
        I_bin_sigma_filter = 10
        n_bin_sigma_filter = 200
        n_rejection_iterations = iparams.n_rejection_cycle
        for i_rejection in range(n_rejection_iterations):
            binner_merge = miller_array_merge.setup_binner(n_bins=n_bin_sigma_filter)
            binner_merge_indices = binner_merge.bin_indices()
            i_seq = flex.int([j for j in range(len(miller_array_merge.data()))])
            i_seq_sel = flex.int()
            for i_bin in range(1, n_bin_sigma_filter + 1):
                i_binner = binner_merge_indices == i_bin
                if len(miller_array_merge.data().select(i_binner)) > 0:
                    I_obs_bin = miller_array_merge.data().select(i_binner)
                    i_seq_bin = i_seq.select(i_binner)
                    med_I_bin = np.median(I_obs_bin)
                    i_filter = (
                        flex.abs((I_obs_bin - med_I_bin) / np.std(I_obs_bin))
                        > I_bin_sigma_filter
                    )
                    i_seq_bin_filter = i_seq_bin.select(i_filter)
                    i_seq_sel.extend(i_seq_bin_filter)
            flag_sel = flex.bool([True] * len(miller_array_merge.data()))
            for i_i_seq_sel in i_seq_sel:
                flag_sel[i_i_seq_sel] = False
            miller_array_merge, I_even, I_odd, I_even_h, I_odd_h, I_even_k, I_odd_k, I_even_l, I_odd_l, r_meas_w_top, r_meas_w_btm, r_meas_top, r_meas_btm, multiplicity = self.params_selection(
                flag_sel,
                miller_array_merge,
                I_even,
                I_odd,
                I_even_h,
                I_odd_h,
                I_even_k,
                I_odd_k,
                I_even_l,
                I_odd_l,
                r_meas_w_top,
                r_meas_w_btm,
                r_meas_top,
                r_meas_btm,
                multiplicity,
            )
        n_refl_outliers = (
            n_refl_all - n_refl_out_resolutions - len(miller_array_merge.data())
        )
        # get iso if given
        flag_hklisoin_found = False
        if iparams.hklisoin is not None:
            flag_hklisoin_found = True
            from iotbx import reflection_file_reader

            reflection_file_iso = reflection_file_reader.any_reflection_file(
                iparams.hklisoin
            )
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
                    miller_array_converted_to_intensity = (
                        miller_array.as_intensity_array()
                    )
            if is_found_iso_as_intensity_array == False:
                if is_found_iso_as_amplitude_array:
                    miller_array_iso = miller_array_converted_to_intensity.deep_copy()
                else:
                    flag_hklisoin_found = False
        # deflating sigI
        # new_sigmas = miller_array_merge.sigmas()/3.0
        # miller_array_merge = miller_array_merge.customized_copy(sigmas=new_sigmas)
        """
    miller_array_merge.show_summary()
    x = miller_array_merge.sigmas().as_numpy_array()
    mu = np.mean(x)
    med = np.median(x)
    sigma = np.std(x)
    num_bins = 20
    plt.subplot(211)
    plt.hist(x, num_bins, normed=0, facecolor='green', alpha=0.5)
    plt.ylabel('Frequencies')
    plt.title('sigI distribution\nmean %5.3f median %5.3f sigma %5.3f' %(mu, med, sigma))
    x = miller_array_merge.as_amplitude_array().sigmas().as_numpy_array()
    miller_array_merge.as_amplitude_array().show_summary()
    mu = np.mean(x)
    med = np.median(x)
    sigma = np.std(x)
    num_bins = 20
    plt.subplot(212)
    plt.hist(x, num_bins, normed=0, facecolor='green', alpha=0.5)
    plt.ylabel('Frequencies')
    plt.title('sigF distribution\nmean %5.3f median %5.3f sigma %5.3f' %(mu, med, sigma))
    plt.show()
    """
        # write as mtz file
        miller_array_merge_unique = miller_array_merge.merge_equivalents().array()
        info = miller.array_info(wavelength=wavelength_mean)
        miller_array_merge_unique.set_info(info)
        mtz_dataset_merge = miller_array_merge_unique.as_mtz_dataset(
            column_root_label="IOBS"
        )
        mtz_dataset_merge.mtz_object().write(
            file_name=iparams.run_no + "/mtz/" + str(output_mtz_file_prefix) + ".mtz"
        )
        # write as cns file
        f_cns = open(
            iparams.run_no + "/mtz/" + str(output_mtz_file_prefix) + ".hkl", "w"
        )
        miller_array_merge_unique.export_as_cns_hkl(file_object=f_cns)
        f_cns.close()
        # calculate isotropic B-factor
        try:
            from mod_util import mx_handler

            mxh = mx_handler()
            asu_contents = mxh.get_asu_contents(iparams.n_residues)
            observations_as_f = miller_array_merge.as_amplitude_array()
            observations_as_f.setup_binner(auto_binning=True)
            from cctbx import statistics

            wp = statistics.wilson_plot(
                observations_as_f, asu_contents, e_statistics=True
            )
            B_merged = wp.wilson_b
        except Exception:
            B_merged = 0
        # calculate total cc_anom for two halves
        cc_anom_acentric, cc_anom_centric, nrefl_anom_acentric, nrefl_anom_centric = (
            0,
            0,
            0,
            0,
        )
        if miller_array_merge.anomalous_flag():
            miller_array_merge_even = miller_array_merge.customized_copy(data=I_even)
            miller_array_merge_odd = miller_array_merge.customized_copy(data=I_odd)
            ma_anom_dif_even = miller_array_merge_even.anomalous_differences()
            ma_anom_dif_odd = miller_array_merge_odd.anomalous_differences()
            ma_anom_centric_flags = ma_anom_dif_even.centric_flags()
            anom_dif_even = ma_anom_dif_even.data()
            anom_dif_odd = ma_anom_dif_odd.data()
            anom_dif_centric_flags = ma_anom_centric_flags.data()
            i_acentric = anom_dif_centric_flags == False
            i_centric = anom_dif_centric_flags == True
            anom_dif_even_acentric = anom_dif_even.select(i_acentric)
            anom_dif_even_centric = anom_dif_even.select(i_centric)
            anom_dif_odd_acentric = anom_dif_odd.select(i_acentric)
            anom_dif_odd_centric = anom_dif_odd.select(i_centric)
            mat_anom_acentric = np.corrcoef(
                anom_dif_even_acentric, anom_dif_odd_acentric
            )
            mat_anom_centric = np.corrcoef(anom_dif_even_centric, anom_dif_odd_centric)
            if len(mat_anom_acentric) > 0:
                cc_anom_acentric = mat_anom_acentric[0, 1]
            if len(mat_anom_centric) > 0:
                cc_anom_centric = mat_anom_centric[0, 1]
            nrefl_anom_acentric = len(anom_dif_even_acentric)
            nrefl_anom_centric = len(anom_dif_even_centric)
            if iparams.flag_plot:
                plt.subplot(211)
                plt.scatter(
                    anom_dif_even_acentric,
                    anom_dif_odd_acentric,
                    s=10,
                    marker="x",
                    c="r",
                )
                plt.title(
                    "CCanoma=%5.2f N_refl=%6.0f"
                    % (cc_anom_acentric, nrefl_anom_acentric)
                )
                plt.xlabel("delta_I_even")
                plt.ylabel("delta_I_odd")
                plt.subplot(212)
                plt.scatter(
                    anom_dif_even_centric, anom_dif_odd_centric, s=10, marker="x", c="r"
                )
                plt.title(
                    "CCanomc=%5.2f N_refl=%6.0f" % (cc_anom_centric, nrefl_anom_centric)
                )
                plt.xlabel("delta_I_even")
                plt.ylabel("delta_I_odd")
                plt.show()
        # select single cone reflections on the three crystal axes
        fraction_percent = iparams.percent_cone_fraction
        miller_array_merge_astar = miller_array_merge.remove_cone(
            fraction_percent, axis_point_2=(1, 0, 0), negate=True
        )
        miller_array_merge_bstar = miller_array_merge.remove_cone(
            fraction_percent, axis_point_2=(0, 1, 0), negate=True
        )
        miller_array_merge_cstar = miller_array_merge.remove_cone(
            fraction_percent, axis_point_2=(0, 0, 1), negate=True
        )
        # report binning stats
        binner_template_asu = miller_array_template_asu.setup_binner(
            n_bins=iparams.n_bins
        )
        binner_template_asu_indices = binner_template_asu.bin_indices()
        txt_out = "\n"
        txt_out += "Isotropic B-factor:  %7.2f\n" % (B_merged)
        txt_out += "No. of reflections\n"
        txt_out += " all:                %7.0f\n" % (n_refl_all)
        txt_out += " outside resolution: %7.0f\n" % (n_refl_out_resolutions)
        txt_out += " outliers:           %7.0f\n" % (n_refl_outliers)
        txt_out += " total left:         %7.0f\n" % (len(miller_array_merge.data()))
        txt_out += "Summary for " + str(output_mtz_file_prefix) + "_merge.mtz\n"
        txt_out += "Bin Resolution Range     Completeness      <N_obs> |Rmerge  Rsplit   CC1/2   N_ind |CCiso   N_ind|CCanoma  N_ind| <I/sigI>   <I>    <sigI>    <I**2>\n"
        txt_out += "--------------------------------------------------------------------------------------------------------------------------------------------------\n"
        sum_r_meas_w_top, sum_r_meas_w_btm, sum_r_meas_top, sum_r_meas_btm, sum_refl_obs, sum_refl_complete, n_refl_obs_total = (
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        cc12_list = []
        avgI_star_list = []
        cc12_n_refl_list = []
        avgI_list = []
        avgI_n_refl_list = []
        I_even_astar = flex.double()
        I_odd_astar = flex.double()
        I_even_bstar = flex.double()
        I_odd_bstar = flex.double()
        I_even_cstar = flex.double()
        I_odd_cstar = flex.double()
        secmom_I_acen_list = flex.double()
        centric_flags = miller_array_merge.centric_flags()
        # collect data for stat. pickle
        sp_res = []
        sp_complete = []
        sp_n_obs = []
        sp_cc12 = []
        sp_rmerge = []
        sp_i_o_sigi = []
        sp_isqr = []
        for i in range(1, iparams.n_bins + 1):
            i_binner = binner_template_asu_indices == i
            miller_indices_bin = miller_array_template_asu.indices().select(i_binner)
            matches_template = miller.match_multi_indices(
                miller_indices_unique=miller_indices_bin,
                miller_indices=miller_array_merge.indices(),
            )
            I_bin = flex.double(
                [
                    miller_array_merge.data()[pair[1]]
                    for pair in matches_template.pairs()
                ]
            )
            sigI_bin = flex.double(
                [
                    miller_array_merge.sigmas()[pair[1]]
                    for pair in matches_template.pairs()
                ]
            )
            miller_indices_obs_bin = flex.miller_index(
                [
                    miller_array_merge.indices()[pair[1]]
                    for pair in matches_template.pairs()
                ]
            )
            centric_flags_bin = flex.bool(
                [centric_flags.data()[pair[1]] for pair in matches_template.pairs()]
            )
            I_acentric_bin = I_bin.select(centric_flags_bin == False)
            secmom_I_acen_bin = np.mean(I_acentric_bin ** 2) / (
                np.mean(I_acentric_bin) ** 2
            )
            secmom_I_acen_list.append(secmom_I_acen_bin)
            # caculate CCanom for the two halves.
            cc_anom_bin_acentric, cc_anom_bin_centric, nrefl_anom_bin_acentric, nrefl_anom_bin_centric = (
                0,
                0,
                0,
                0,
            )
            if miller_array_merge.anomalous_flag():
                matches_anom_dif_even = miller.match_multi_indices(
                    miller_indices_unique=miller_indices_bin,
                    miller_indices=ma_anom_dif_even.indices(),
                )
                anom_dif_even = flex.double(
                    [
                        ma_anom_dif_even.data()[pair[1]]
                        for pair in matches_anom_dif_even.pairs()
                    ]
                )
                anom_dif_centric_flags = flex.bool(
                    [
                        ma_anom_centric_flags.data()[pair[1]]
                        for pair in matches_anom_dif_even.pairs()
                    ]
                )
                matches_anom_dif_odd = miller.match_multi_indices(
                    miller_indices_unique=miller_indices_bin,
                    miller_indices=ma_anom_dif_odd.indices(),
                )
                anom_dif_odd = flex.double(
                    [
                        ma_anom_dif_odd.data()[pair[1]]
                        for pair in matches_anom_dif_odd.pairs()
                    ]
                )
                i_acentric = anom_dif_centric_flags == False
                i_centric = anom_dif_centric_flags == True
                anom_dif_even_acentric = anom_dif_even.select(i_acentric)
                anom_dif_even_centric = anom_dif_even.select(i_centric)
                anom_dif_odd_acentric = anom_dif_odd.select(i_acentric)
                anom_dif_odd_centric = anom_dif_odd.select(i_centric)
                mat_anom_acentric = np.corrcoef(
                    anom_dif_even_acentric, anom_dif_odd_acentric
                )
                mat_anom_centric = np.corrcoef(
                    anom_dif_even_centric, anom_dif_odd_centric
                )
                if len(mat_anom_acentric) > 0:
                    cc_anom_bin_acentric = mat_anom_acentric[0, 1]
                if len(mat_anom_centric) > 0:
                    cc_anom_bin_centric = mat_anom_centric[0, 1]
                nrefl_anom_bin_acentric = len(anom_dif_even_acentric)
                nrefl_anom_bin_centric = len(anom_dif_even_centric)
            # prepare the calculation of these parameters
            mean_i_over_sigi_bin, multiplicity_bin, r_meas_w_bin, r_meas_bin, n_refl_cc12_bin, r_split_bin = (
                0,
                0,
                0,
                0,
                0,
                0,
            )
            cc12_bin, cc12_bin_astar, cc12_bin_bstar, cc12_bin_cstar = (0, 0, 0, 0)
            avgI_bin, avgI_bin_h, avgI_bin_k, avgI_bin_l = (0, 0, 0, 0)
            avgI_bin_astar, avgI_bin_bstar, avgI_bin_cstar = (0, 0, 0)
            if len(I_bin) > 0:
                # calculate <I>
                avgI_bin = flex.mean(I_bin)
                mean_i_over_sigi_bin = flex.mean(I_bin / sigI_bin)
                # calculation of Rmeas
                r_meas_w_top_bin = flex.double(
                    [r_meas_w_top[pair[1]] for pair in matches_template.pairs()]
                )
                r_meas_w_btm_bin = flex.double(
                    [r_meas_w_btm[pair[1]] for pair in matches_template.pairs()]
                )
                r_meas_top_bin = flex.double(
                    [r_meas_top[pair[1]] for pair in matches_template.pairs()]
                )
                r_meas_btm_bin = flex.double(
                    [r_meas_btm[pair[1]] for pair in matches_template.pairs()]
                )
                multiplicity_bin = flex.double(
                    [multiplicity[pair[1]] for pair in matches_template.pairs()]
                )
                sum_r_meas_w_top_bin, sum_r_meas_w_btm_bin, sum_r_meas_top_bin, sum_r_meas_btm_bin, sum_mul_bin = (
                    sum(r_meas_w_top_bin),
                    sum(r_meas_w_btm_bin),
                    sum(r_meas_top_bin),
                    sum(r_meas_btm_bin),
                    sum(multiplicity_bin),
                )
                sum_r_meas_w_top += sum_r_meas_w_top_bin
                sum_r_meas_w_btm += sum_r_meas_w_btm_bin
                sum_r_meas_top += sum_r_meas_top_bin
                sum_r_meas_btm += sum_r_meas_btm_bin
                n_refl_obs_total += sum_mul_bin
                multiplicity_bin = sum_mul_bin / len(I_bin)
                if sum_r_meas_w_btm_bin > 0:
                    r_meas_w_bin = sum_r_meas_w_top_bin / sum_r_meas_w_btm_bin
                else:
                    r_meas_w_bin = float("Inf")
                if sum_r_meas_btm_bin > 0:
                    r_meas_bin = sum_r_meas_top_bin / sum_r_meas_btm_bin
                else:
                    r_meas_bin = float("Inf")
                # filter I_even and I_odd for this bin and select only >0 values
                I_even_bin = flex.double(
                    [I_even[pair[1]] for pair in matches_template.pairs()]
                )
                I_odd_bin = flex.double(
                    [I_odd[pair[1]] for pair in matches_template.pairs()]
                )
                i_even_filter_sel = I_even_bin > 0
                I_even_bin_sel = I_even_bin.select(i_even_filter_sel)
                I_odd_bin_sel = I_odd_bin.select(i_even_filter_sel)
                miller_indices_bin_sel = miller_indices_obs_bin.select(
                    i_even_filter_sel
                )
                n_refl_halfset_bin = len(I_even_bin_sel)
                # calculation of CC1/2 and <I> on the three crystal axes (a*, b*, c*) ---------------
                if n_refl_halfset_bin > 0:
                    cc12_bin = np.corrcoef(I_even_bin_sel, I_odd_bin_sel)[0, 1]
                    r_split_bin = (1 / math.sqrt(2)) * (
                        flex.sum(flex.abs(I_even_bin_sel - I_odd_bin_sel))
                        / (flex.sum(I_even_bin_sel + I_odd_bin_sel) * 0.5)
                    )

                I_even_bin_astar = flex.double()
                I_odd_bin_astar = flex.double()
                I_even_bin_bstar = flex.double()
                I_odd_bin_bstar = flex.double()
                I_even_bin_cstar = flex.double()
                I_odd_bin_cstar = flex.double()
                try:
                    matches_astar = miller.match_multi_indices(
                        miller_indices_unique=miller_array_merge_astar.indices(),
                        miller_indices=miller_indices_bin_sel,
                    )
                    I_even_bin_astar = flex.double(
                        [I_even_bin_sel[pair[1]] for pair in matches_astar.pairs()]
                    )
                    I_odd_bin_astar = flex.double(
                        [I_odd_bin_sel[pair[1]] for pair in matches_astar.pairs()]
                    )

                    if len(I_even_bin_astar) > 0:
                        cc12_bin_astar = np.corrcoef(I_even_bin_astar, I_odd_bin_astar)[
                            0, 1
                        ]
                        avgI_bin_astar = flex.mean(I_even_bin_astar)
                    I_even_astar.extend(I_even_bin_astar)
                    I_odd_astar.extend(I_odd_bin_astar)
                except Exception:
                    dummy = 1
                try:
                    matches_bstar = miller.match_multi_indices(
                        miller_indices_unique=miller_array_merge_bstar.indices(),
                        miller_indices=miller_indices_bin_sel,
                    )
                    I_even_bin_bstar = flex.double(
                        [I_even_bin_sel[pair[1]] for pair in matches_bstar.pairs()]
                    )
                    I_odd_bin_bstar = flex.double(
                        [I_odd_bin_sel[pair[1]] for pair in matches_bstar.pairs()]
                    )

                    if len(I_even_bin_bstar) > 0:
                        cc12_bin_bstar = np.corrcoef(I_even_bin_bstar, I_odd_bin_bstar)[
                            0, 1
                        ]
                        avgI_bin_bstar = flex.mean(I_even_bin_bstar)
                    I_even_bstar.extend(I_even_bin_bstar)
                    I_odd_bstar.extend(I_odd_bin_bstar)
                except Exception:
                    dummy = 1
                try:
                    matches_cstar = miller.match_multi_indices(
                        miller_indices_unique=miller_array_merge_cstar.indices(),
                        miller_indices=miller_indices_bin_sel,
                    )
                    I_even_bin_cstar = flex.double(
                        [I_even_bin_sel[pair[1]] for pair in matches_cstar.pairs()]
                    )
                    I_odd_bin_cstar = flex.double(
                        [I_odd_bin_sel[pair[1]] for pair in matches_cstar.pairs()]
                    )

                    if len(I_even_bin_cstar) > 0:
                        cc12_bin_cstar = np.corrcoef(I_even_bin_cstar, I_odd_bin_cstar)[
                            0, 1
                        ]
                        avgI_bin_cstar = flex.mean(I_even_bin_cstar)
                    I_even_cstar.extend(I_even_bin_cstar)
                    I_odd_cstar.extend(I_odd_bin_cstar)
                except Exception:
                    dummy = 1
                # caculation of <I> on the three lab axes (h,k,l) ---------------------------------
                I_even_h_bin = flex.double(
                    [I_even_h[pair[1]] for pair in matches_template.pairs()]
                )
                I_odd_h_bin = flex.double(
                    [I_odd_h[pair[1]] for pair in matches_template.pairs()]
                )
                I_even_k_bin = flex.double(
                    [I_even_k[pair[1]] for pair in matches_template.pairs()]
                )
                I_odd_k_bin = flex.double(
                    [I_odd_k[pair[1]] for pair in matches_template.pairs()]
                )
                I_even_l_bin = flex.double(
                    [I_even_l[pair[1]] for pair in matches_template.pairs()]
                )
                I_odd_l_bin = flex.double(
                    [I_odd_l[pair[1]] for pair in matches_template.pairs()]
                )
                if len(I_even_h_bin.select(I_even_h_bin > 0)) > 0:
                    avgI_bin_h = flex.mean(I_even_h_bin.select(I_even_h_bin > 0))
                if len(I_even_k_bin.select(I_even_k_bin > 0)) > 0:
                    avgI_bin_k = flex.mean(I_even_k_bin.select(I_even_k_bin > 0))
                if len(I_even_l_bin.select(I_even_l_bin > 0)) > 0:
                    avgI_bin_l = flex.mean(I_even_l_bin.select(I_even_l_bin > 0))
            # collect CC1/2 and <I> on the crystal axes
            cc12_list.append([cc12_bin, cc12_bin_astar, cc12_bin_bstar, cc12_bin_cstar])
            avgI_star_list.append(
                [avgI_bin, avgI_bin_astar, avgI_bin_bstar, avgI_bin_cstar]
            )
            cc12_n_refl_list.append(
                [
                    n_refl_halfset_bin,
                    len(I_even_bin_astar),
                    len(I_even_bin_bstar),
                    len(I_even_bin_cstar),
                ]
            )
            # collect <I> on the lab axes
            avgI_list.append([avgI_bin, avgI_bin_h, avgI_bin_k, avgI_bin_l])
            avgI_n_refl_list.append(
                [
                    len(I_bin),
                    len(I_even_h_bin.select(I_even_h_bin > 0)),
                    len(I_even_k_bin.select(I_even_k_bin > 0)),
                    len(I_even_l_bin.select(I_even_l_bin > 0)),
                ]
            )
            completeness = len(miller_indices_obs_bin) / len(miller_indices_bin)
            sum_refl_obs += len(miller_indices_obs_bin)
            sum_refl_complete += len(miller_indices_bin)
            # calculate CCiso
            cc_iso_bin = 0
            r_iso_bin = 0
            n_refl_cciso_bin = 0
            if flag_hklisoin_found:
                matches_iso = miller.match_multi_indices(
                    miller_indices_unique=miller_array_iso.indices(),
                    miller_indices=miller_indices_obs_bin,
                )
                I_iso = flex.double(
                    [miller_array_iso.data()[pair[0]] for pair in matches_iso.pairs()]
                )
                I_merge_match_iso = flex.double(
                    [I_bin[pair[1]] for pair in matches_iso.pairs()]
                )
                sigI_merge_match_iso = flex.double(
                    [sigI_bin[pair[1]] for pair in matches_iso.pairs()]
                )
                n_refl_cciso_bin = len(matches_iso.pairs())
                if len(matches_iso.pairs()) > 0:
                    cc_iso_bin = np.corrcoef(I_merge_match_iso, I_iso)[0, 1]
                    r_iso_bin = 0
            # collect txt out
            txt_out += (
                "%02d %7.2f - %7.2f %5.1f %6.0f / %6.0f %7.2f %7.2f %7.2f %7.2f %6.0f %7.2f %6.0f %7.2f %6.0f %8.2f %10.1f %8.1f %6.2f"
                % (
                    i,
                    binner_template_asu.bin_d_range(i)[0],
                    binner_template_asu.bin_d_range(i)[1],
                    completeness * 100,
                    len(miller_indices_obs_bin),
                    len(miller_indices_bin),
                    multiplicity_bin,
                    r_meas_bin * 100,
                    r_split_bin * 100,
                    cc12_bin * 100,
                    n_refl_halfset_bin,
                    cc_iso_bin * 100,
                    n_refl_cciso_bin,
                    cc_anom_bin_acentric,
                    nrefl_anom_bin_acentric,
                    mean_i_over_sigi_bin,
                    np.mean(I_bin),
                    np.mean(sigI_bin),
                    secmom_I_acen_bin,
                )
            )
            txt_out += "\n"
            # collect data for stat.pickle
            sp_res.append(binner_template_asu.bin_d_range(i)[1])
            sp_complete.append(completeness * 100)
            sp_n_obs.append(multiplicity_bin)
            sp_cc12.append(cc12_bin * 100)
            sp_rmerge.append(r_meas_bin * 100)
            sp_i_o_sigi.append(mean_i_over_sigi_bin)
            sp_isqr.append(secmom_I_acen_bin)
        # calculate CCiso
        cc_iso = 0
        n_refl_iso = 0
        if flag_hklisoin_found:
            matches_iso = miller.match_multi_indices(
                miller_indices_unique=miller_array_iso.indices(),
                miller_indices=miller_array_merge.indices(),
            )
            I_iso = flex.double(
                [miller_array_iso.data()[pair[0]] for pair in matches_iso.pairs()]
            )
            I_merge_match_iso = flex.double(
                [miller_array_merge.data()[pair[1]] for pair in matches_iso.pairs()]
            )
            sigI_merge_match_iso = flex.double(
                [miller_array_merge.sigmas()[pair[1]] for pair in matches_iso.pairs()]
            )
            if len(matches_iso.pairs()) > 0:
                cc_iso = np.corrcoef(I_merge_match_iso, I_iso)[0, 1]
                n_refl_iso = len(matches_iso.pairs())
                r_iso = 0
            if iparams.flag_plot:
                plt.scatter(I_iso, I_merge_match_iso, s=10, marker="x", c="r")
                plt.title("CC=%.4g" % (cc_iso))
                plt.xlabel("I_ref")
                plt.ylabel("I_obs")
                plt.show()
        # calculate cc12
        i_even_filter_sel = I_even > 0
        cc12, cc12_astar, cc12_bstar, cc12_cstar, r_split, n_refl_half_total = (
            0,
            0,
            0,
            0,
            0,
            0,
        )
        try:
            I_even_filter = I_even.select(i_even_filter_sel)
            I_odd_filter = I_odd.select(i_even_filter_sel)
            cc12 = np.corrcoef(I_even_filter, I_odd_filter)[0, 1]
            cc12_astar = np.corrcoef(I_even_astar, I_odd_astar)[0, 1]
            cc12_bstar = np.corrcoef(I_even_bstar, I_odd_bstar)[0, 1]
            cc12_cstar = np.corrcoef(I_even_cstar, I_odd_cstar)[0, 1]
            r_split = (1 / math.sqrt(2)) * (
                flex.sum(flex.abs(I_even_filter - I_odd_filter))
                / (flex.sum(I_even_filter + I_odd_filter) * 0.5)
            )
            n_refl_half_total = len(I_even_filter)
        except Exception:
            dummy = 0
        # calculate Qmeas and Qw
        if sum_r_meas_w_btm > 0:
            r_meas_w = sum_r_meas_w_top / sum_r_meas_w_btm
        else:
            r_meas_w = float("Inf")
        if sum_r_meas_btm > 0:
            r_meas = sum_r_meas_top / sum_r_meas_btm
        else:
            r_meas = float("Inf")
        # save data for stat. pickle in stat_dict
        stat_dict = {
            "binned_resolution": [sp_res],
            "binned_completeness": [sp_complete],
            "binned_n_obs": [sp_n_obs],
            "binned_cc12": [sp_cc12],
            "binned_rmerge": [sp_rmerge],
            "binned_i_o_sigi": [sp_i_o_sigi],
            "binned_isqr": [sp_isqr],
            "total_res_max": [miller_array_merge.d_max_min()[0]],
            "total_res_min": [miller_array_merge.d_max_min()[1]],
            "total_completeness": [(sum_refl_obs / sum_refl_complete) * 100],
            "total_n_obs": [n_refl_obs_total / sum_refl_obs],
            "total_cc12": [cc12 * 100],
            "total_rmerge": [r_meas * 100],
            "total_i_o_sigi": [
                np.mean(miller_array_merge.data() / miller_array_merge.sigmas())
            ],
            "space_group_info": [miller_array_merge.space_group_info()],
        }
        psh = pickle_stat_handler()
        psh.write_pickle(iparams, stat_dict)
        txt_out += "--------------------------------------------------------------------------------------------------------------------------------------------------\n"
        txt_out += (
            "        TOTAL        %5.1f %6.0f / %6.0f %7.2f %7.2f %7.2f %7.2f %6.0f %7.2f %6.0f %7.2f %6.0f %8.2f %10.1f %8.1f %6.2f\n"
            % (
                (sum_refl_obs / sum_refl_complete) * 100,
                sum_refl_obs,
                sum_refl_complete,
                n_refl_obs_total / sum_refl_obs,
                r_meas * 100,
                r_split * 100,
                cc12 * 100,
                len(I_even.select(i_even_filter_sel)),
                cc_iso * 100,
                n_refl_iso,
                cc_anom_acentric,
                nrefl_anom_acentric,
                np.mean(miller_array_merge.data() / miller_array_merge.sigmas()),
                np.mean(miller_array_merge.data()),
                np.mean(miller_array_merge.sigmas()),
                np.mean(secmom_I_acen_list),
            )
        )
        txt_out += "--------------------------------------------------------------------------------------------------------------------------------------------------\n"
        txt_out += "\n"
        # output CC1/2 on the three crystal axes
        txt_out += "Summary of CC1/2 on three crystal axes\n"
        txt_out += "Bin Resolution Range                CC1/2                                <I>                               N_refl           \n"
        txt_out += "                        All      a*      b*      c*  |   All         a*        b*        c*      | All      a*      b*     c* \n"
        txt_out += "-------------------------------------------------------------------------------------------------------------------------------\n"
        cn12_n_sum, cc12_n_astar_sum, cc12_n_bstar_sum, cc12_n_cstar_sum = (0, 0, 0, 0)
        for i in range(1, iparams.n_bins + 1):
            i_binner = binner_template_asu_indices == i
            _cc12, _cc12_astar, _cc12_bstar, _cc12_cstar = cc12_list[i - 1]
            _cc12_n, _cc12_n_astar, _cc12_n_bstar, _cc12_n_cstar = cc12_n_refl_list[
                i - 1
            ]
            _avgI, _avgI_astar, _avgI_bstar, _avgI_cstar = avgI_star_list[i - 1]
            cn12_n_sum += _cc12_n
            cc12_n_astar_sum += _cc12_n_astar
            cc12_n_bstar_sum += _cc12_n_bstar
            cc12_n_cstar_sum += _cc12_n_cstar
            txt_out += (
                "%02d %7.2f - %7.2f %7.2f %7.2f %7.2f %7.2f %10.1f %10.1f %10.1f %10.1f %6.0f %6.0f %6.0f %6.0f\n"
                % (
                    i,
                    binner_template_asu.bin_d_range(i)[0],
                    binner_template_asu.bin_d_range(i)[1],
                    _cc12 * 100,
                    _cc12_astar * 100,
                    _cc12_bstar * 100,
                    _cc12_cstar * 100,
                    _avgI,
                    _avgI_astar,
                    _avgI_bstar,
                    _avgI_cstar,
                    _cc12_n,
                    _cc12_n_astar,
                    _cc12_n_bstar,
                    _cc12_n_cstar,
                )
            )

        txt_out += "-------------------------------------------------------------------------------------------------------------------------------\n"
        txt_out += (
            "        TOTAL        %7.2f %7.2f %7.2f %7.2f %10.1f %10.1f %10.1f %10.1f %6.0f %6.0f %6.0f %6.0f\n"
            % (
                cc12 * 100,
                cc12_astar * 100,
                cc12_bstar * 100,
                cc12_cstar * 100,
                np.mean(miller_array_merge.data()),
                np.mean(I_even_astar),
                np.mean(I_even_bstar),
                np.mean(I_even_cstar),
                cn12_n_sum,
                cc12_n_astar_sum,
                cc12_n_bstar_sum,
                cc12_n_cstar_sum,
            )
        )
        txt_out += "-------------------------------------------------------------------------------------------------------------------------------\n"
        txt_out += "\n"
        """
    #output <I> on the three lab coordinates
    txt_out += 'Summary of <I> on the three lab coordinates\n'
    txt_out += 'Bin Resolution Range                  <I>                             N_refl        \n'
    txt_out += '                        All       h=0       k=0      l=0  | All    h=0    k=0    l=0\n'
    txt_out += '------------------------------------------------------------------------------------\n'
    avgI_n_sum, avgI_n_h_sum, avgI_n_k_sum, avgI_n_l_sum = (0,0,0,0)
    for i in range(1,iparams.n_bins+1):
      i_binner = (binner_template_asu_indices == i)
      _avgI_n, _avgI_n_h, _avgI_n_k, _avgI_n_l = avgI_n_refl_list[i-1]
      _avgI, _avgI_h, _avgI_k, _avgI_l = avgI_list[i-1]
      avgI_n_sum += _avgI_n
      avgI_n_h_sum += _avgI_n_h
      avgI_n_k_sum += _avgI_n_k
      avgI_n_l_sum += _avgI_n_l
      txt_out += '%02d %7.2f - %7.2f %8.2f %8.2f %8.2f %8.2f %6.0f %6.0f %6.0f %6.0f\n' \
          %(i, binner_template_asu.bin_d_range(i)[0], binner_template_asu.bin_d_range(i)[1], \
          _avgI, _avgI_h, _avgI_k, _avgI_l,
          _avgI_n, _avgI_n_h, _avgI_n_k, _avgI_n_l)

    txt_out += '------------------------------------------------------------------------------------\n'
    txt_out += '        TOTAL        %8.2f %8.2f %8.2f %8.2f %6.0f %6.0f %6.0f %6.0f\n' \
          %(np.mean(miller_array_merge.data()), np.mean(I_even_h.select(I_even_h>0)), np.mean(I_even_k.select(I_even_k>0)), np.mean(I_even_l.select(I_even_l>0)), \
          avgI_n_sum, avgI_n_h_sum, avgI_n_k_sum, avgI_n_l_sum)
    txt_out += '------------------------------------------------------------------------------------\n'
    txt_out += '\n'
    """
        return miller_array_merge, txt_out

    def plot_stats(self, results, iparams):
        # retrieve stats from results and plot them
        if iparams.flag_plot or iparams.flag_output_verbose:
            # get expected f^2
            try:
                from mod_util import mx_handler

                mxh = mx_handler()
                asu_contents = mxh.get_asu_contents(iparams.n_residues)
                observations_as_f = results[0].observations.as_amplitude_array()
                binner_template_asu = observations_as_f.setup_binner(
                    n_bins=iparams.n_bins
                )
                from cctbx import statistics

                wp = statistics.wilson_plot(
                    observations_as_f, asu_contents, e_statistics=True
                )
                expected_f_sq = wp.expected_f_sq
                mean_stol_sq = wp.mean_stol_sq
            except Exception:
                expected_f_sq = flex.double([0] * iparams.n_bins)
                mean_stol_sq = flex.double(range(iparams.n_bins))
            # setup list
            G_frame = flex.double()
            B_frame = flex.double()
            rotx_frame = flex.double()
            roty_frame = flex.double()
            ry_frame = flex.double()
            rz_frame = flex.double()
            re_frame = flex.double()
            uc_a_frame = flex.double()
            uc_b_frame = flex.double()
            uc_c_frame = flex.double()
            uc_alpha_frame = flex.double()
            uc_beta_frame = flex.double()
            uc_gamma_frame = flex.double()
            SE_all = flex.double()
            R_sq_all = flex.double()
            cc_all = flex.double()
            mean_I_frame = []
            mean_I_scaled_frame = []
            txt_out_verbose = ""
            for pres in results:
                # collect parameters
                G_frame.append(pres.G)
                B_frame.append(pres.B)
                rotx_frame.append(pres.rotx * 180 / math.pi)
                roty_frame.append(pres.roty * 180 / math.pi)
                ry_frame.append(pres.ry)
                rz_frame.append(pres.rz)
                re_frame.append(pres.re)
                uc_a_frame.append(pres.uc_params[0])
                uc_b_frame.append(pres.uc_params[1])
                uc_c_frame.append(pres.uc_params[2])
                uc_alpha_frame.append(pres.uc_params[3])
                uc_beta_frame.append(pres.uc_params[4])
                uc_gamma_frame.append(pres.uc_params[5])
                SE_all.append(pres.SE)
                R_sq_all.append(pres.R_sq)
                cc_all.append(pres.CC_final)
                try:
                    # collect <I>
                    pres.observations.setup_binner(n_bins=iparams.n_bins)
                    mean_I_frame.append(
                        flex.double(pres.observations.mean(use_binning=True).data[1:-1])
                    )
                    # collect <I> scaled
                    sin_theta_over_lambda_sq = (
                        pres.observations.two_theta(pres.wavelength)
                        .sin_theta_over_lambda_sq()
                        .data()
                    )
                    I_full = flex.double(
                        pres.observations.data()
                        / (
                            pres.G
                            * flex.exp(
                                flex.double(-2 * pres.B * sin_theta_over_lambda_sq)
                            )
                        )
                    )
                    sigI_full = flex.double(
                        pres.observations.sigmas()
                        / (
                            pres.G
                            * flex.exp(
                                flex.double(-2 * pres.B * sin_theta_over_lambda_sq)
                            )
                        )
                    )
                    obs_scaled = pres.observations.customized_copy(
                        data=I_full, sigmas=sigI_full
                    )
                    obs_scaled.setup_binner(n_bins=iparams.n_bins)
                    mean_I_scaled_frame.append(
                        flex.double(obs_scaled.mean(use_binning=True).data[1:-1])
                    )
                    # decorate text output
                except Exception:
                    pass
                txt_out_verbose += (
                    "%8.1f %8.1f %8.1f %8.2f %6.2f %6.2f %6.2f %6.2f %8.5f %8.5f %8.5f %8.5f %6.2f %8.2f %8.2f %8.2f %8.2f %8.2f %8.2f %6.2f "
                    % (
                        pres.R_init,
                        pres.R_final,
                        pres.R_xy_init,
                        pres.R_xy_final,
                        pres.G,
                        pres.B,
                        pres.rotx * 180 / math.pi,
                        pres.roty * 180 / math.pi,
                        pres.ry,
                        pres.rz,
                        pres.r0,
                        pres.re,
                        pres.voigt_nu,
                        pres.uc_params[0],
                        pres.uc_params[1],
                        pres.uc_params[2],
                        pres.uc_params[3],
                        pres.uc_params[4],
                        pres.uc_params[5],
                        pres.CC_final,
                    )
                    + pres.pickle_filename
                    + "\n"
                )
        if iparams.flag_output_verbose:
            import os

            fileseq_list = flex.int()
            for file_in in os.listdir(iparams.run_no + "/hist"):
                if file_in.endswith(".paramhist"):
                    file_split = file_in.split(".")
                    fileseq_list.append(int(file_split[0]))
            if len(fileseq_list) == 0:
                new_fileseq = 0
            else:
                new_fileseq = flex.max(fileseq_list) + 1
            newfile_name = str(new_fileseq) + ".paramhist"
            f = open(iparams.run_no + "/hist/" + newfile_name, "w")
            f.write(txt_out_verbose)
            f.close()
        if iparams.flag_plot:
            num_bins = 10
            # plot <I> before and after applying scale factors
            plt.subplot(121)
            for y_data in mean_I_frame:
                plt.plot(mean_stol_sq, flex.log(y_data), color="teal")
            plt.grid(True)
            plt.ylim([2, 10])
            plt.title("Mean intensity before scaling")
            plt.subplot(122)
            for y_data in mean_I_scaled_frame:
                plt.plot(mean_stol_sq, flex.log(y_data), color="teal")
            plt.plot(
                mean_stol_sq,
                flex.log(expected_f_sq) / 1.75,
                color="maroon",
                linewidth=2.0,
            )
            plt.grid(True)
            plt.ylim([2, 10])
            plt.title("Mean intensity after scaling")
            plt.show()
            plt.subplot(121)
            x = SE_all.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "SE distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(122)
            x = cc_all.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "CC distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.show()
            plt.subplot(241)
            x = G_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "G distribution\nmean %5.3f median %5.3f sigma %5.3f" % (mu, med, sigma)
            )
            plt.subplot(242)
            x = B_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "B distribution\nmean %5.3f median %5.3f sigma %5.3f" % (mu, med, sigma)
            )
            plt.subplot(243)
            x = rotx_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "Delta rot_x distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(244)
            x = roty_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "Delta rot_y distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(245)
            x = ry_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "ry distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(246)
            x = rz_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "rz distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(247)
            x = re_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "re distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.show()
            plt.subplot(231)
            x = uc_a_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "a distribution\nmean %5.3f median %5.3f sigma %5.3f" % (mu, med, sigma)
            )
            plt.subplot(232)
            x = uc_b_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "b distribution\nmean %5.3f median %5.3f sigma %5.3f" % (mu, med, sigma)
            )
            plt.subplot(233)
            x = uc_c_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "c distribution\nmean %5.3f median %5.3f sigma %5.3f" % (mu, med, sigma)
            )
            plt.subplot(234)
            x = uc_alpha_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "alpha distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(235)
            x = uc_beta_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "beta distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.subplot(236)
            x = uc_gamma_frame.as_numpy_array()
            mu, med, sigma = (np.mean(x), np.median(x), np.std(x))
            plt.hist(x, num_bins, normed=0, facecolor="green", alpha=0.5)
            plt.ylabel("Frequencies")
            plt.title(
                "gamma distribution\nmean %5.3f median %5.3f sigma %5.3f"
                % (mu, med, sigma)
            )
            plt.show()


class basis_handler(object):
    """classdocs."""

    def __init__(self):
        """Constructor."""

    def calc_direct_space_matrix(self, my_unit_cell, rotation_matrix):

        # calculate the conversion matrix (from fractional to cartesian coordinates
        frac2cart_matrix = my_unit_cell.orthogonalization_matrix()
        frac2cart_matrix = sqr(frac2cart_matrix)

        # calculate direct_space matrix
        direct_space_matrix = frac2cart_matrix.transpose() * rotation_matrix

        return direct_space_matrix


class svd_handler(object):
    """Singular value decomposion Solve linear equations with best fit
    basis."""

    # Input: expects Nx3 matrix of points
    # Returns R,t
    # R = 3x3 rotation matrix
    # t = 3x1 column vector
    def __init__(self):
        """Constructor."""

    def rigid_transform_3D(self, A, B):
        assert len(A) == len(B)
        N = A.shape[0]
        # total points
        centroid_A = np.mean(A, axis=0)
        centroid_B = np.mean(B, axis=0)
        # centre the points
        AA = A - np.tile(centroid_A, (N, 1))
        BB = B - np.tile(centroid_B, (N, 1))
        # dot is matrix multiplication for array
        H = np.transpose(AA) * BB
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T * U.T
        # special reflection case
        if np.linalg.det(R) < 0:
            # print "Reflection detected"
            Vt[2, :] *= -1
            R = Vt.T * U.T
        t = -R * centroid_A.T + centroid_B.T
        return R, t


class wilson_plot_handler(object):
    """Take miller array and show Wilson Plot."""

    def __init__(self):
        """Constructor."""

    def show_plot(self, miller_array_in, n_bins=None):
        if n_bins is None:
            binner = miller_array_in.setup_binner(auto_binning=True)
        else:
            binner = miller_array_in.setup_binner(n_bins=n_bins)
        binner_indices = binner.bin_indices()
        avg_I_bin = flex.double()
        one_dsqr_bin = flex.double()
        for i in range(1, n_bins + 1):
            i_binner = binner_indices == i
            I_sel = observations_original.data().select(i_binner)
            avg_I_bin.append(np.mean(I_sel))
            one_dsqr_bin.append(1 / binner.bin_d_range(i)[1] ** 2)
        x_axis = one_dsqr_bin
        import matplotlib.pyplot as plt

        fig, ax1 = plt.subplots()
        ln1 = ax1.plot(x_axis, avg_I_bin, linestyle="-", linewidth=2.0, c="b")
        ax1.set_xlabel("1/d^2")
        ax1.set_ylabel("<I>", color="b")
        plt.grid()
        plt.show()


class mx_handler(object):
    """
    Author      : Uervirojnangkoorn, M.
    Created     : 8/15/2015
    A collection of macromolecular-crystallagphic wrapper functions
    """

    def __init__(self):
        """Constructor."""

    def get_asu_contents(self, n_residues):
        asu_contents = None
        if n_residues > 0:
            asu_contents = {
                "H": 8.0 * float(n_residues),
                "C": 5.0 * float(n_residues),
                "N": 1.5 * float(n_residues),
                "O": 1.2 * float(n_residues),
            }
        return asu_contents


class misc_handler(object):
    """
    Author      : Uervirojnangkoorn, M.
    Created     : 1/6/2016
    A collection of misc. functions
    """

    def __init__(self):
        """Constructor."""

    def get_resolution_step_for_B(self, iparams):
        resolution_gap = 7 - iparams.scale.d_min
        resolution_step = resolution_gap / iparams.n_bins
        return resolution_step


class pickle_stat_handler(object):
    """
    Author      : Uervirojnangkoorn, M.
    Created     : 5/19/2016
    A class to handle writing out statistic info. pickle.
    """

    def __init__(self):
        """Constructor."""

    def write_pickle(self, iparams, stat_dict):
        import os
        import cPickle as pickle

        fname = iparams.run_no + "/pickle.stat"
        if os.path.isfile(fname):
            pickle_stat = pickle.load(open(fname, "rb"))
            for key in stat_dict.keys():
                if key in pickle_stat.keys():
                    pickle_stat[key].append(stat_dict[key][0])
                else:
                    pickle_stat[key] = stat_dict[key]
            pickle.dump(pickle_stat, open(fname, "wb"))
        else:
            pickle.dump(stat_dict, open(fname, "wb"))

    def read_pickle(self, iparams):
        import os
        import cPickle as pickle

        fname = iparams.run_no + "/pickle.stat"
        if os.path.isfile(fname):
            pickle_stat = pickle.load(open(fname, "rb"))
            for key in pickle_stat.keys():
                data = pickle_stat[key]
                print "key:", key, " size:", len(data)
                for d in data:
                    print d
