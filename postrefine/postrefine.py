from __future__ import division
from cctbx.array_family import flex
from cctbx import miller
import cPickle as pickle
from mod_util import intensities_scaler
from mod_leastsqr import leastsqr_handler
from mod_results import postref_results
from cctbx.crystal import symmetry
import math
from scitbx.matrix import sqr
from cctbx import statistics
from mod_partiality import partiality_handler
from mod_lbfgs_partiality import lbfgs_partiality_handler


class postref_handler(object):
    """handle post-refinement.

    - read-in and store input in input_handler object
    - generate a mean-intensity-scaled mtz file as a reference set
    - perform post-refinement
    """

    def __init__(self):
        """Constructor."""

    def organize_input(
        self, observations_pickle, iparams, avg_mode, pickle_filename=None
    ):
        """Given the pickle file, extract and prepare observations object and
        the alpha angle (meridional to equatorial)."""
        if iparams.isoform_name is not None:
            if "identified_isoform" not in observations_pickle:
                return None, "No identified isoform"
            if observations_pickle["identified_isoform"] != iparams.isoform_name:
                return (
                    None,
                    "Identified isoform(%s) is not the requested isoform (%s)"
                    % (observations_pickle["identified_isoform"], iparams.isoform_name),
                )
        if iparams.flag_weak_anomalous:
            if avg_mode == "final":
                target_anomalous_flag = iparams.target_anomalous_flag
            else:
                target_anomalous_flag = False
        else:
            target_anomalous_flag = iparams.target_anomalous_flag
        img_filename_only = ""
        if pickle_filename is not None:
            pickle_filepaths = pickle_filename.split("/")
            img_filename_only = pickle_filepaths[len(pickle_filepaths) - 1]
        txt_exception = " {0:40} ==> ".format(img_filename_only)
        observations = observations_pickle["observations"][0]
        detector_distance_mm = observations_pickle["distance"]
        mm_predictions = iparams.pixel_size_mm * (
            observations_pickle["mapped_predictions"][0]
        )
        xbeam = observations_pickle["xbeam"]
        ybeam = observations_pickle["ybeam"]
        alpha_angle_obs = flex.double(
            [
                math.atan(abs(pred[0] - xbeam) / abs(pred[1] - ybeam))
                for pred in mm_predictions
            ]
        )
        spot_pred_x_mm = flex.double([pred[0] - xbeam for pred in mm_predictions])
        spot_pred_y_mm = flex.double([pred[1] - ybeam for pred in mm_predictions])
        # Polarization correction
        wavelength = observations_pickle["wavelength"]
        if iparams.flag_LP_correction:
            fx = 1 - iparams.polarization_horizontal_fraction
            fy = 1 - fx
            if fx > 1.0 or fx < 0:
                print "Horizontal polarization fraction is not correct. The value must be >= 0 and <= 1"
                print "No polarization correction. Continue with post-refinement"
            else:
                phi_angle_obs = flex.double(
                    [
                        math.atan2(pred[1] - ybeam, pred[0] - xbeam)
                        for pred in mm_predictions
                    ]
                )
                bragg_angle_obs = observations.two_theta(wavelength).data()
                P = (
                    fx
                    * (
                        (flex.sin(phi_angle_obs) ** 2)
                        + (
                            (flex.cos(phi_angle_obs) ** 2)
                            * flex.cos(bragg_angle_obs) ** 2
                        )
                    )
                ) + (
                    fy
                    * (
                        (flex.cos(phi_angle_obs) ** 2)
                        + (
                            (flex.sin(phi_angle_obs) ** 2)
                            * flex.cos(bragg_angle_obs) ** 2
                        )
                    )
                )
                I_prime = observations.data() / P
                sigI_prime = observations.sigmas() / P
                observations = observations.customized_copy(
                    data=flex.double(I_prime), sigmas=flex.double(sigI_prime)
                )
        # set observations with target space group - !!! required for correct
        # merging due to map_to_asu command.
        if iparams.target_crystal_system is not None:
            target_crystal_system = iparams.target_crystal_system
        else:
            target_crystal_system = (
                observations.crystal_symmetry().space_group().crystal_system()
            )
        lph = lbfgs_partiality_handler()
        if iparams.flag_override_unit_cell:
            uc_constrained_inp = lph.prep_input(
                iparams.target_unit_cell.parameters(), target_crystal_system
            )
        else:
            uc_constrained_inp = lph.prep_input(
                observations.unit_cell().parameters(), target_crystal_system
            )
        uc_constrained = list(
            lph.prep_output(uc_constrained_inp, target_crystal_system)
        )
        try:
            # apply constrain using the crystal system
            miller_set = symmetry(
                unit_cell=uc_constrained, space_group_symbol=iparams.target_space_group
            ).build_miller_set(
                anomalous_flag=target_anomalous_flag, d_min=iparams.merge.d_min
            )
            observations = observations.customized_copy(
                anomalous_flag=target_anomalous_flag,
                crystal_symmetry=miller_set.crystal_symmetry(),
            )
        except Exception:
            a, b, c, alpha, beta, gamma = uc_constrained
            txt_exception += (
                "Mismatch spacegroup (%6.2f,%6.2f,%6.2f,%6.2f,%6.2f,%6.2f)"
                % (a, b, c, alpha, beta, gamma)
            )
            print txt_exception
            return None, txt_exception
        # reset systematic absence
        sys_absent_negate_flags = flex.bool(
            [
                sys_absent_flag[1] == False
                for sys_absent_flag in observations.sys_absent_flags()
            ]
        )
        observations = observations.select(sys_absent_negate_flags)
        alpha_angle_obs = alpha_angle_obs.select(sys_absent_negate_flags)
        spot_pred_x_mm = spot_pred_x_mm.select(sys_absent_negate_flags)
        spot_pred_y_mm = spot_pred_y_mm.select(sys_absent_negate_flags)
        import os.path

        # remove observations from rejection list
        if os.path.isfile(iparams.run_no + "/rejections.txt"):
            txt_out = (
                pickle_filename
                + " \nN_before_rejection: "
                + str(len(observations.data()))
                + "\n"
            )
            file_reject = open(iparams.run_no + "/rejections.txt", "r")
            data_reject = file_reject.read().split("\n")
            miller_indices_ori_rejected = flex.miller_index()
            for row_reject in data_reject:
                col_reject = row_reject.split()
                if len(col_reject) > 0:
                    if col_reject[0].strip() == pickle_filename:
                        miller_indices_ori_rejected.append(
                            (
                                int(col_reject[1].strip()),
                                int(col_reject[2].strip()),
                                int(col_reject[3].strip()),
                            )
                        )
            if len(miller_indices_ori_rejected) > 0:
                i_sel_flag = flex.bool([True] * len(observations.data()))
                for miller_index_ori_rejected in miller_indices_ori_rejected:
                    i_index_ori = 0
                    for miller_index_ori in observations.indices():
                        if miller_index_ori_rejected == miller_index_ori:
                            i_sel_flag[i_index_ori] = False
                            txt_out += (
                                " -Discard:"
                                + str(miller_index_ori[0])
                                + ","
                                + str(miller_index_ori[1])
                                + ","
                                + str(miller_index_ori[2])
                                + "\n"
                            )
                        i_index_ori += 1
                observations = observations.customized_copy(
                    indices=observations.indices().select(i_sel_flag),
                    data=observations.data().select(i_sel_flag),
                    sigmas=observations.sigmas().select(i_sel_flag),
                )
                alpha_angle_obs = alpha_angle_obs.select(i_sel_flag)
                spot_pred_x_mm = spot_pred_x_mm.select(i_sel_flag)
                spot_pred_y_mm = spot_pred_y_mm.select(i_sel_flag)
                txt_out += "N_after_rejection: " + str(len(observations.data())) + "\n"
        # filter resolution
        i_sel_res = observations.resolution_filter_selection(
            d_max=iparams.merge.d_max, d_min=iparams.merge.d_min
        )
        observations = observations.select(i_sel_res)
        alpha_angle_obs = alpha_angle_obs.select(i_sel_res)
        spot_pred_x_mm = spot_pred_x_mm.select(i_sel_res)
        spot_pred_y_mm = spot_pred_y_mm.select(i_sel_res)
        # Filter weak
        i_sel = (observations.data() / observations.sigmas()) > iparams.merge.sigma_min
        observations = observations.select(i_sel)
        alpha_angle_obs = alpha_angle_obs.select(i_sel)
        spot_pred_x_mm = spot_pred_x_mm.select(i_sel)
        spot_pred_y_mm = spot_pred_y_mm.select(i_sel)
        # filter icering (if on)
        if iparams.icering.flag_on:
            miller_indices = flex.miller_index()
            I_set = flex.double()
            sigI_set = flex.double()
            alpha_angle_obs_set = flex.double()
            spot_pred_x_mm_set = flex.double()
            spot_pred_y_mm_set = flex.double()
            for miller_index, d, I, sigI, alpha, spot_x, spot_y in zip(
                observations.indices(),
                observations.d_spacings().data(),
                observations.data(),
                observations.sigmas(),
                alpha_angle_obs,
                spot_pred_x_mm,
                spot_pred_y_mm,
            ):
                if d > iparams.icering.d_upper or d < iparams.icering.d_lower:
                    miller_indices.append(miller_index)
                    I_set.append(I)
                    sigI_set.append(sigI)
                    alpha_angle_obs_set.append(alpha)
                    spot_pred_x_mm_set.append(spot_x)
                    spot_pred_y_mm_set.append(spot_y)
            observations = observations.customized_copy(
                indices=miller_indices, data=I_set, sigmas=sigI_set
            )
            alpha_angle_obs = alpha_angle_obs_set[:]
            spot_pred_x_mm = spot_pred_x_mm_set[:]
            spot_pred_y_mm = spot_pred_y_mm_set[:]
        # replacing sigI (if set)
        if iparams.flag_replace_sigI:
            observations = observations.customized_copy(
                sigmas=flex.sqrt(observations.data())
            )
        inputs = (
            observations,
            alpha_angle_obs,
            spot_pred_x_mm,
            spot_pred_y_mm,
            detector_distance_mm,
        )
        return inputs, "OK"

    def determine_polar(
        self, observations_original, iparams, pickle_filename, pres=None
    ):
        """Determine polarity based on input data.

        The function still needs isomorphous reference so, if flag_polar
        is True, miller_array_iso must be supplied in input file.
        """
        if iparams.indexing_ambiguity.flag_on == False:
            return "h,k,l", 0, 0
        cc_asu = 0
        cc_rev = 0
        if iparams.indexing_ambiguity.index_basis_in is not None:
            if iparams.indexing_ambiguity.index_basis_in.endswith("mtz"):
                # use reference mtz file to determine polarity
                from iotbx import reflection_file_reader

                reflection_file_polar = reflection_file_reader.any_reflection_file(
                    iparams.indexing_ambiguity.index_basis_in
                )
                miller_arrays_polar = reflection_file_polar.as_miller_arrays()
                miller_array_polar = miller_arrays_polar[0]
                miller_array_polar = miller_array_polar.resolution_filter(
                    d_min=iparams.indexing_ambiguity.d_min,
                    d_max=iparams.indexing_ambiguity.d_max,
                )
                # for post-refinement, apply the scale factors and partiality first
                if pres is not None:
                    # observations_original = pres.observations_original.deep_copy()
                    two_theta = observations_original.two_theta(
                        wavelength=pres.wavelength
                    ).data()
                    alpha_angle = flex.double(
                        [0] * len(observations_original.indices())
                    )
                    spot_pred_x_mm = flex.double(
                        [0] * len(observations_original.indices())
                    )
                    spot_pred_y_mm = flex.double(
                        [0] * len(observations_original.indices())
                    )
                    detector_distance_mm = pres.detector_distance_mm
                    ph = partiality_handler()
                    partiality, dummy, dummy, dummy = ph.calc_partiality_anisotropy_set(
                        pres.unit_cell,
                        0,
                        0,
                        observations_original.indices(),
                        pres.ry,
                        pres.rz,
                        pres.r0,
                        pres.re,
                        two_theta,
                        alpha_angle,
                        pres.wavelength,
                        pres.crystal_orientation,
                        spot_pred_x_mm,
                        spot_pred_y_mm,
                        detector_distance_mm,
                        iparams.partiality_model,
                        iparams.flag_beam_divergence,
                    )
                    # partiality = pres.partiality
                    sin_theta_over_lambda_sq = (
                        observations_original.two_theta(pres.wavelength)
                        .sin_theta_over_lambda_sq()
                        .data()
                    )
                    I_full = flex.double(
                        observations_original.data()
                        / (
                            pres.G
                            * flex.exp(
                                flex.double(-2 * pres.B * sin_theta_over_lambda_sq)
                            )
                            * partiality
                        )
                    )
                    sigI_full = flex.double(
                        observations_original.sigmas()
                        / (
                            pres.G
                            * flex.exp(
                                flex.double(-2 * pres.B * sin_theta_over_lambda_sq)
                            )
                            * partiality
                        )
                    )
                    observations_original = observations_original.customized_copy(
                        data=I_full, sigmas=sigI_full
                    )
                observations_asu = observations_original.map_to_asu()
                observations_rev = self.get_observations_non_polar(
                    observations_original, iparams.indexing_ambiguity.assigned_basis
                )
                matches = miller.match_multi_indices(
                    miller_indices_unique=miller_array_polar.indices(),
                    miller_indices=observations_asu.indices(),
                )
                I_ref_match = flex.double(
                    [miller_array_polar.data()[pair[0]] for pair in matches.pairs()]
                )
                I_obs_match = flex.double(
                    [observations_asu.data()[pair[1]] for pair in matches.pairs()]
                )
                cc_asu = flex.linear_correlation(I_ref_match, I_obs_match).coefficient()
                n_refl_asu = len(matches.pairs())
                matches = miller.match_multi_indices(
                    miller_indices_unique=miller_array_polar.indices(),
                    miller_indices=observations_rev.indices(),
                )
                I_ref_match = flex.double(
                    [miller_array_polar.data()[pair[0]] for pair in matches.pairs()]
                )
                I_obs_match = flex.double(
                    [observations_rev.data()[pair[1]] for pair in matches.pairs()]
                )
                cc_rev = flex.linear_correlation(I_ref_match, I_obs_match).coefficient()
                n_refl_rev = len(matches.pairs())
                polar_hkl = "h,k,l"
                if cc_rev > (cc_asu * 1.01):
                    polar_hkl = iparams.indexing_ambiguity.assigned_basis
            else:
                # use basis in the given input file
                polar_hkl = "h,k,l"
                basis_pickle = pickle.load(
                    open(iparams.indexing_ambiguity.index_basis_in, "rb")
                )
                if pickle_filename in basis_pickle:
                    polar_hkl = basis_pickle[pickle_filename]
        else:
            # set default polar_hkl to h,k,l
            polar_hkl = "h,k,l"
        return polar_hkl, cc_asu, cc_rev

    def get_observations_non_polar(self, observations_original, polar_hkl):
        # return observations with correct polarity
        observations_asu = observations_original.map_to_asu()
        assert len(observations_original.indices()) == len(
            observations_asu.indices()
        ), (
            "No. of original and asymmetric-unit indices are not equal %6.0f, %6.0f"
            % (len(observations_original.indices()), len(observations_asu.indices()))
        )
        if polar_hkl == "h,k,l":
            return observations_asu
        else:
            from cctbx import sgtbx

            cb_op = sgtbx.change_of_basis_op(polar_hkl)
            observations_rev = observations_asu.change_basis(cb_op).map_to_asu()
            assert len(observations_original.indices()) == len(
                observations_rev.indices()
            ), (
                "No. of original and inversed asymmetric-unit indices are not equal %6.0f, %6.0f"
                % (
                    len(observations_original.indices()),
                    len(observations_rev.indices()),
                )
            )
            return observations_rev

    def postrefine_by_frame(
        self, frame_no, pickle_filename, iparams, miller_array_ref, pres_in, avg_mode
    ):
        # 1. Prepare data
        observations_pickle = pickle.load(open(pickle_filename, "rb"))
        crystal_init_orientation = observations_pickle["current_orientation"][0]
        wavelength = observations_pickle["wavelength"]
        pickle_filepaths = pickle_filename.split("/")
        img_filename_only = pickle_filepaths[len(pickle_filepaths) - 1]
        txt_exception = " {0:40} ==> ".format(img_filename_only)
        inputs, txt_organize_input = self.organize_input(
            observations_pickle, iparams, avg_mode, pickle_filename=pickle_filename
        )
        if inputs is not None:
            observations_original, alpha_angle, spot_pred_x_mm, spot_pred_y_mm, detector_distance_mm = (
                inputs
            )
        else:
            txt_exception += txt_organize_input + "\n"
            return None, txt_exception
        # 2. Determine polarity - always do this even if flag_polar = False
        # the function will take care of it.
        polar_hkl, cc_iso_raw_asu, cc_iso_raw_rev = self.determine_polar(
            observations_original, iparams, pickle_filename, pres=pres_in
        )
        # 3. Select data for post-refinement (only select indices that are common with the reference set
        observations_non_polar = self.get_observations_non_polar(
            observations_original, polar_hkl
        )
        matches = miller.match_multi_indices(
            miller_indices_unique=miller_array_ref.indices(),
            miller_indices=observations_non_polar.indices(),
        )
        I_ref_match = flex.double(
            [miller_array_ref.data()[pair[0]] for pair in matches.pairs()]
        )
        miller_indices_ref_match = flex.miller_index(
            (miller_array_ref.indices()[pair[0]] for pair in matches.pairs())
        )
        I_obs_match = flex.double(
            [observations_non_polar.data()[pair[1]] for pair in matches.pairs()]
        )
        sigI_obs_match = flex.double(
            [observations_non_polar.sigmas()[pair[1]] for pair in matches.pairs()]
        )
        miller_indices_original_obs_match = flex.miller_index(
            (observations_original.indices()[pair[1]] for pair in matches.pairs())
        )
        miller_indices_non_polar_obs_match = flex.miller_index(
            (observations_non_polar.indices()[pair[1]] for pair in matches.pairs())
        )
        alpha_angle_set = flex.double(
            [alpha_angle[pair[1]] for pair in matches.pairs()]
        )
        spot_pred_x_mm_set = flex.double(
            [spot_pred_x_mm[pair[1]] for pair in matches.pairs()]
        )
        spot_pred_y_mm_set = flex.double(
            [spot_pred_y_mm[pair[1]] for pair in matches.pairs()]
        )
        references_sel = miller_array_ref.customized_copy(
            data=I_ref_match, indices=miller_indices_ref_match
        )
        observations_original_sel = observations_original.customized_copy(
            data=I_obs_match,
            sigmas=sigI_obs_match,
            indices=miller_indices_original_obs_match,
        )
        observations_non_polar_sel = observations_non_polar.customized_copy(
            data=I_obs_match,
            sigmas=sigI_obs_match,
            indices=miller_indices_non_polar_obs_match,
        )
        # 4. Do least-squares refinement
        lsqrh = leastsqr_handler()
        try:
            refined_params, stats, n_refl_postrefined = lsqrh.optimize(
                I_ref_match,
                observations_original_sel,
                wavelength,
                crystal_init_orientation,
                alpha_angle_set,
                spot_pred_x_mm_set,
                spot_pred_y_mm_set,
                iparams,
                pres_in,
                observations_non_polar_sel,
                detector_distance_mm,
            )
        except Exception:
            txt_exception += "optimization failed.\n"
            return None, txt_exception
        # caculate partiality for output (with target_anomalous check)
        G_fin, B_fin, rotx_fin, roty_fin, ry_fin, rz_fin, r0_fin, re_fin, voigt_nu_fin, a_fin, b_fin, c_fin, alpha_fin, beta_fin, gamma_fin = (
            refined_params
        )
        inputs, txt_organize_input = self.organize_input(
            observations_pickle, iparams, avg_mode, pickle_filename=pickle_filename
        )
        observations_original, alpha_angle, spot_pred_x_mm, spot_pred_y_mm, detector_distance_mm = (
            inputs
        )
        observations_non_polar = self.get_observations_non_polar(
            observations_original, polar_hkl
        )
        from cctbx.uctbx import unit_cell

        uc_fin = unit_cell((a_fin, b_fin, c_fin, alpha_fin, beta_fin, gamma_fin))
        if pres_in is not None:
            crystal_init_orientation = pres_in.crystal_orientation
        two_theta = observations_original.two_theta(wavelength=wavelength).data()
        ph = partiality_handler()
        partiality_fin, dummy, rs_fin, rh_fin = ph.calc_partiality_anisotropy_set(
            uc_fin,
            rotx_fin,
            roty_fin,
            observations_original.indices(),
            ry_fin,
            rz_fin,
            r0_fin,
            re_fin,
            voigt_nu_fin,
            two_theta,
            alpha_angle,
            wavelength,
            crystal_init_orientation,
            spot_pred_x_mm,
            spot_pred_y_mm,
            detector_distance_mm,
            iparams.partiality_model,
            iparams.flag_beam_divergence,
        )
        # calculate the new crystal orientation
        O = sqr(uc_fin.orthogonalization_matrix()).transpose()
        R = sqr(crystal_init_orientation.crystal_rotation_matrix()).transpose()
        from cctbx.crystal_orientation import crystal_orientation, basis_type

        CO = crystal_orientation(O * R, basis_type.direct)
        crystal_fin_orientation = CO.rotate_thru((1, 0, 0), rotx_fin).rotate_thru(
            (0, 1, 0), roty_fin
        )
        # remove reflections with partiality below threshold
        i_sel = partiality_fin > iparams.merge.partiality_min
        partiality_fin_sel = partiality_fin.select(i_sel)
        rs_fin_sel = rs_fin.select(i_sel)
        rh_fin_sel = rh_fin.select(i_sel)
        observations_non_polar_sel = observations_non_polar.customized_copy(
            indices=observations_non_polar.indices().select(i_sel),
            data=observations_non_polar.data().select(i_sel),
            sigmas=observations_non_polar.sigmas().select(i_sel),
        )
        observations_original_sel = observations_original.customized_copy(
            indices=observations_original.indices().select(i_sel),
            data=observations_original.data().select(i_sel),
            sigmas=observations_original.sigmas().select(i_sel),
        )
        pres = postref_results()
        pres.set_params(
            observations=observations_non_polar_sel,
            observations_original=observations_original_sel,
            refined_params=refined_params,
            stats=stats,
            partiality=partiality_fin_sel,
            rs_set=rs_fin_sel,
            rh_set=rh_fin_sel,
            frame_no=frame_no,
            pickle_filename=pickle_filename,
            wavelength=wavelength,
            crystal_orientation=crystal_fin_orientation,
            detector_distance_mm=detector_distance_mm,
        )
        r_change, r_xy_change, cc_change, cc_iso_change = (0, 0, 0, 0)
        try:
            r_change = ((pres.R_final - pres.R_init) / pres.R_init) * 100
            r_xy_change = ((pres.R_xy_final - pres.R_xy_init) / pres.R_xy_init) * 100
            cc_change = ((pres.CC_final - pres.CC_init) / pres.CC_init) * 100
            cc_iso_change = (
                (pres.CC_iso_final - pres.CC_iso_init) / pres.CC_iso_init
            ) * 100
        except Exception:
            pass
        txt_postref = " {0:40} ==> RES:{1:5.2f} NREFL:{2:5d} R:{3:8.2f}% RXY:{4:8.2f}% CC:{5:6.2f}% CCISO:{6:6.2f}% G:{7:10.3e} B:{8:7.1f} CELL:{9:6.2f} {10:6.2f} {11:6.2f} {12:6.2f} {13:6.2f} {14:6.2f}".format(
            img_filename_only + " (" + polar_hkl + ")",
            observations_original_sel.d_min(),
            len(observations_original_sel.data()),
            r_change,
            r_xy_change,
            cc_change,
            cc_iso_change,
            pres.G,
            pres.B,
            a_fin,
            b_fin,
            c_fin,
            alpha_fin,
            beta_fin,
            gamma_fin,
        )
        print txt_postref
        txt_postref += "\n"
        return pres, txt_postref

    def calc_mean_intensity(self, pickle_filename, iparams, avg_mode):
        observations_pickle = pickle.load(open(pickle_filename, "rb"))
        wavelength = observations_pickle["wavelength"]
        pickle_filepaths = pickle_filename.split("/")
        txt_exception = " {0:40} ==> ".format(
            pickle_filepaths[len(pickle_filepaths) - 1]
        )
        inputs, txt_organize_input = self.organize_input(
            observations_pickle, iparams, avg_mode, pickle_filename=pickle_filename
        )
        if inputs is not None:
            observations_original, alpha_angle_obs, spot_pred_x_mm, spot_pred_y_mm, detector_distance_mm = (
                inputs
            )
        else:
            txt_exception += txt_organize_input + "\n"
            return None, txt_exception
        # filter resolution
        observations_sel = observations_original.resolution_filter(
            d_min=iparams.scale.d_min, d_max=iparams.scale.d_max
        )
        # filer sigma
        i_sel = (
            observations_sel.data() / observations_sel.sigmas()
        ) > iparams.scale.sigma_min
        if len(observations_sel.data().select(i_sel)) == 0:
            return None, txt_exception
        mean_I = flex.median(observations_sel.data().select(i_sel))
        return mean_I, txt_exception + "ok"

    def scale_frame_by_mean_I(
        self, frame_no, pickle_filename, iparams, mean_of_mean_I, avg_mode
    ):
        observations_pickle = pickle.load(open(pickle_filename, "rb"))
        pickle_filepaths = pickle_filename.split("/")
        img_filename_only = pickle_filepaths[len(pickle_filepaths) - 1]
        inputs, txt_organize_input = self.organize_input(
            observations_pickle, iparams, avg_mode, pickle_filename=pickle_filename
        )
        txt_exception = " {0:40} ==> ".format(img_filename_only)
        if inputs is not None:
            observations_original, alpha_angle, spot_pred_x_mm, spot_pred_y_mm, detector_distance_mm = (
                inputs
            )
        else:
            txt_exception += txt_organize_input + "\n"
            return None, txt_exception
        wavelength = observations_pickle["wavelength"]
        crystal_init_orientation = observations_pickle["current_orientation"][0]
        # select only reflections matched with scale input params.
        # filter by resolution
        i_sel_res = observations_original.resolution_filter_selection(
            d_min=iparams.scale.d_min, d_max=iparams.scale.d_max
        )
        observations_original_sel = observations_original.select(i_sel_res)
        alpha_angle_sel = alpha_angle.select(i_sel_res)
        spot_pred_x_mm_sel = spot_pred_x_mm.select(i_sel_res)
        spot_pred_y_mm_sel = spot_pred_y_mm.select(i_sel_res)
        # filter by sigma
        i_sel_sigmas = (
            observations_original_sel.data() / observations_original_sel.sigmas()
        ) > iparams.scale.sigma_min
        observations_original_sel = observations_original_sel.select(i_sel_sigmas)
        alpha_angle_sel = alpha_angle_sel.select(i_sel_sigmas)
        spot_pred_x_mm_sel = spot_pred_x_mm_sel.select(i_sel_sigmas)
        spot_pred_y_mm_sel = spot_pred_y_mm_sel.select(i_sel_sigmas)
        polar_hkl, cc_iso_raw_asu, cc_iso_raw_rev = self.determine_polar(
            observations_original, iparams, pickle_filename
        )
        observations_non_polar_sel = self.get_observations_non_polar(
            observations_original_sel, polar_hkl
        )
        observations_non_polar = self.get_observations_non_polar(
            observations_original, polar_hkl
        )
        uc_params = observations_original.unit_cell().parameters()
        ph = partiality_handler()
        r0 = ph.calc_spot_radius(
            sqr(crystal_init_orientation.reciprocal_matrix()),
            observations_original_sel.indices(),
            wavelength,
        )
        # calculate first G
        (G, B) = (1, 0)
        stats = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        if mean_of_mean_I > 0:
            G = flex.median(observations_original_sel.data()) / mean_of_mean_I
        if iparams.flag_apply_b_by_frame:
            try:
                from mod_util import mx_handler

                mxh = mx_handler()
                asu_contents = mxh.get_asu_contents(iparams.n_residues)
                observations_as_f = observations_non_polar_sel.as_amplitude_array()
                binner_template_asu = observations_as_f.setup_binner(auto_binning=True)
                wp = statistics.wilson_plot(
                    observations_as_f, asu_contents, e_statistics=True
                )
                G = wp.wilson_intensity_scale_factor * 1e3
                B = wp.wilson_b
            except Exception:
                txt_exception += "warning B-factor calculation failed.\n"
                return None, txt_exception
        two_theta = observations_original.two_theta(wavelength=wavelength).data()
        sin_theta_over_lambda_sq = (
            observations_original.two_theta(wavelength=wavelength)
            .sin_theta_over_lambda_sq()
            .data()
        )
        ry, rz, re, voigt_nu, rotx, roty = (
            0,
            0,
            iparams.gamma_e,
            iparams.voigt_nu,
            0,
            0,
        )
        partiality_init, delta_xy_init, rs_init, rh_init = ph.calc_partiality_anisotropy_set(
            crystal_init_orientation.unit_cell(),
            rotx,
            roty,
            observations_original.indices(),
            ry,
            rz,
            r0,
            re,
            voigt_nu,
            two_theta,
            alpha_angle,
            wavelength,
            crystal_init_orientation,
            spot_pred_x_mm,
            spot_pred_y_mm,
            detector_distance_mm,
            iparams.partiality_model,
            iparams.flag_beam_divergence,
        )
        if iparams.flag_plot_expert:
            n_bins = 20
            binner = observations_original.setup_binner(n_bins=n_bins)
            binner_indices = binner.bin_indices()
            avg_partiality_init = flex.double()
            avg_rs_init = flex.double()
            avg_rh_init = flex.double()
            one_dsqr_bin = flex.double()
            for i in range(1, n_bins + 1):
                i_binner = binner_indices == i
                if len(observations_original.data().select(i_binner)) > 0:
                    print binner.bin_d_range(i)[1], flex.mean(
                        partiality_init.select(i_binner)
                    ), flex.mean(rs_init.select(i_binner)), flex.mean(
                        rh_init.select(i_binner)
                    ), len(
                        partiality_init.select(i_binner)
                    )
        # save results
        refined_params = flex.double(
            [
                G,
                B,
                rotx,
                roty,
                ry,
                rz,
                r0,
                re,
                voigt_nu,
                uc_params[0],
                uc_params[1],
                uc_params[2],
                uc_params[3],
                uc_params[4],
                uc_params[5],
            ]
        )
        pres = postref_results()
        pres.set_params(
            observations=observations_non_polar,
            observations_original=observations_original,
            refined_params=refined_params,
            stats=stats,
            partiality=partiality_init,
            rs_set=rs_init,
            rh_set=rh_init,
            frame_no=frame_no,
            pickle_filename=pickle_filename,
            wavelength=wavelength,
            crystal_orientation=crystal_init_orientation,
            detector_distance_mm=detector_distance_mm,
        )
        txt_scale_frame_by_mean_I = " {0:40} ==> RES:{1:5.2f} NREFL:{2:5d} G:{3:10.3e} B:{4:7.1f} CELL:{5:6.2f} {6:6.2f} {7:6.2f} {8:6.2f} {9:6.2f} {10:6.2f}".format(
            img_filename_only + " (" + polar_hkl + ")",
            observations_original.d_min(),
            len(observations_original_sel.data()),
            G,
            B,
            uc_params[0],
            uc_params[1],
            uc_params[2],
            uc_params[3],
            uc_params[4],
            uc_params[5],
        )
        print txt_scale_frame_by_mean_I
        txt_scale_frame_by_mean_I += "\n"
        return pres, txt_scale_frame_by_mean_I


def prepare_output(results, iparams, avg_mode):
    # results is a list of postref_results objects
    # length of this list equals to number of input frames
    inten_scaler = intensities_scaler()
    prep_output = inten_scaler.prepare_output(results, iparams, avg_mode)
    return prep_output


def calc_avg_I(
    group_no,
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
    pickle_filename,
):
    # results is a list of postref_results objects
    # length of this list equals to number of input frames
    inten_scaler = intensities_scaler()
    avg_I_result = inten_scaler.calc_avg_I(
        group_no,
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
        pickle_filename,
    )
    return avg_I_result


def calc_avg_I_cpp(
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
    pickle_filename,
):
    # results is a list of postref_results objects
    # length of this list equals to number of input frames
    inten_scaler = intensities_scaler()
    avg_I_result = inten_scaler.calc_avg_I_cpp(
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
        pickle_filename,
    )
    return avg_I_result


def write_output(
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
    # results is a list of postref_results objects
    # length of this list equals to number of input frames
    inten_scaler = intensities_scaler()
    miller_array_merge, txt_out = inten_scaler.write_output(
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
    )
    return miller_array_merge, txt_out


def read_input(args):
    from mod_input import process_input

    iparams, txt_out_input = process_input(args)
    return iparams, txt_out_input
