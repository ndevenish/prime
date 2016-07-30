from __future__ import division
import iotbx.phil
from libtbx.utils import Usage, Sorry
import sys, os

master_phil = iotbx.phil.parse(
    """
data = None
  .type = path
  .multiple = True
  .help = Directory containing integrated data in pickle format.  Repeat to \
    specify additional directories.
run_no = None
  .type = str
  .help = Run no. is used as folder name that stores output files.
  .optional = False
title = None
  .type = str
  .help = Title of the run.
  .multiple = False
icering
  .help = "Allowing exclusion of icering."
{
  flag_on = False
    .type = bool
    .help = Turn this flag on to allow exclusion of icering.
  d_upper = 3.9
    .type = float
    .help = Minimum resolution.
  d_lower = 3.85
    .type = float
    .help = Maximum resolution.
}
scale
  .help = "Parameters used to generate mean-intensity scaled reference set."
{
  d_min = 0.1
    .type = float
    .help = Minimum resolution.
  d_max = 99
    .type = float
    .help = Maximum resolution.
  sigma_min = 1.5
    .type = float
    .help = Minimum I/sigI cutoff.
}
postref
  .help = Post-refinement parameters
{
  residual_threshold = 5
    .type = float
    .help = Percent increase in residual allowed during microcycle.
  residual_threshold_xy = 5
    .type = float
    .help = Percent increase in residual (xy) allowed during microcycle.
  scale
    .help = Scale factors
  {
    d_min = 0.1
      .type = float
      .help = Minimum resolution.
    d_max = 99
      .type = float
      .help = Maximum resolution.
    sigma_min = 1.5
      .type = float
      .help = Minimum I/sigI cutoff.
    partiality_min = 0.1
      .type = float
      .help = Minimum partiality cutoff.
  }
  crystal_orientation
    .help = Crystal orientations
  {
    flag_on = True
      .type = bool
      .help = Set to False to turn post-refinement in this section off.
    d_min = 0.1
      .type = float
      .help = Minimum resolution.
    d_max = 99
      .type = float
      .help = Maximum resolution.
    sigma_min = 1.5
      .type = float
      .help = Minimum I/sigI cutoff.
    partiality_min = 0.1
      .type = float
      .help = Minimum partiality cutoff.
  }
  reflecting_range
    .help = Reflecting range
  {
    flag_on = True
      .type = bool
      .help = Set to False to turn post-refinement in this section off.
    d_min = 0.1
      .type = float
      .help = Minimum resolution.
    d_max = 99
      .type = float
      .help = Maximum resolution.
    sigma_min = 1.5
      .type = float
      .help = Minimum I/sigI cutoff.
    partiality_min = 0.1
      .type = float
      .help = Minimum partiality cutoff.
  }
  unit_cell
    .help = Unit-cell dimensions
  {
    flag_on = True
      .type = bool
      .help = Set to False to turn post-refinement in this section off.
    d_min = 0.1
      .type = float
      .help = Minimum resolution.
    d_max = 99
      .type = float
      .help = Maximum resolution.
    sigma_min = 1.5
      .type = float
      .help = Minimum I/sigI cutoff.
    partiality_min = 0.1
      .type = float
      .help = Minimum partiality cutoff.
    uc_tolerance = 5
      .type = float
      .help = Unit-cell tolerance in percent.
  }
  allparams
    .help = All parameters
  {
    flag_on = True
      .type = bool
      .help = Set to True to refine all parameters together.
    d_min = 0.1
      .type = float
      .help = Minimum resolution.
    d_max = 99
      .type = float
      .help = Maximum resolution.
    sigma_min = 1.5
      .type = float
      .help = Minimum I/sigI cutoff.
    partiality_min = 0.1
      .type = float
      .help = Minimum partiality cutoff.
    uc_tolerance = 5
      .type = float
      .help = Unit-cell tolerance in percent.
  }
}
merge
  .help = "Parameters used in merging"
{
  d_min = 0.1
    .type = float
    .help = Minimum resolution.
  d_max = 99
    .type = float
    .help = Maximum resolution.
  sigma_min = -3.0
    .type = float
    .help = Minimum I/sigI cutoff.
  partiality_min = 0.1
    .type = float
    .help = Minimum partiality cutoff.
  uc_tolerance = 5
    .type = float
    .help = Unit-cell tolerance in percent.
}
target_unit_cell = None
  .type = unit_cell
  .help = Target unit-cell parameters are used to discard outlier cells.
  .optional = False
flag_override_unit_cell = False
  .type = bool
  .help = Set to True to overide unit cell in observations with the target cell.
target_space_group = None
  .type = str
  .help = Target space group.
  .optional = False
target_anomalous_flag = False
  .type = bool
  .help = Target anomalous flag (False = Not anomalous data)
  .optional = False
flag_weak_anomalous = False
  .type = bool
  .help = Set to True to indicate that you have weak anomalous signal.
target_crystal_system = None
  .type = str
  .help = Target crystal system
  .optional = True
n_residues = None
  .type = int
  .help = No. of amino acid residues.
indexing_ambiguity
  .help = "Parameters used in resolving indexing ambiguity"
{
  flag_on = False
    .type = bool
    .help = Set to True to allow the program to read in polarity info. \
      from the pickle file specified in index_basis_in.
  index_basis_in = None
    .type = path
    .help = Pickle file storing polarity info. (output from Brehm & \
      Diederichs clustering algorithm).
  assigned_basis = h,k,l
    .type = str
    .help = In case index_basis_in given is an mtz file, you can specify a basis that each integration can be converted to.
  d_min = 3.0
    .type = float
    .help = In case index_basis_in given is an mtz file, you can pecify minimum resolution used to calculate correlation with the given mtz file.
  d_max = 10.0
    .type = float
    .help = In case index_basis_in given is an mtz file, you can pecify maximum resolution used to calculate correlation with the given mtz file.
}
hklisoin = None
  .type = path
  .help = Mtz file for the calculation of CCiso
hklrefin = None
  .type = path
  .help = Mtz file used as a reference in post-refinement.
flag_plot = False
  .type = bool
  .help = Normal plots.
flag_plot_expert = False
  .type = bool
  .help = Expert plots.
flag_force_no_postrefine = False
  .type = bool
  .help = Set to True to output only the mean-intensity scaled merged.
n_postref_cycle = 3
  .type = int
  .help = No. of cycles for post-refinement.
n_postref_sub_cycle = 1
  .type = int
  .help = No. of cycles for the least-squares minimization in post-refinement.
n_rejection_cycle = 1
  .type = int
  .help = No. of cycles for the outlier rejection.
sigma_rejection = 3
  .type = float
  .help = Sigma level for outlier rejection.
n_bins = 20
  .type = int
  .help = No. of bins used to report statistics.
pixel_size_mm = None
  .type = float
  .help = Pixel size in mm. (MAR = 0.079346)
  .optional = False
frame_accept_min_cc = 0.25
  .type = float
  .help = CC cut-off for the rejection of frames before merging.
flag_apply_b_by_frame = True
  .type = bool
  .help = Set to False to dismiss B-factor checking.
b_refine_d_min = 99
  .type = float
  .help = Minimum resolution.
partiality_model = Lorentzian
  .type = str
  .help = Your choice of partiality model: Lorentzian (default), Voigt (in beta test), Lognormal (in beta test).
flag_LP_correction = True
  .type = bool
  .help = Do polarization correction.
flag_volume_correction = True
  .type = bool
  .help = Do volume correction.
flag_beam_divergence = False
  .type = bool
  .help = Default is not to refine beam divergence. Set to True to allow gammaX and gammaY refinement.
n_processors = 32
  .type = int
  .help = No. of processing units
  .optional = True
gamma_e = 0.003
  .type = float
  .help = Initial spread of the energy spectrum (1/Angstrom).
voigt_nu = 0.5
  .type = float
  .help = If select Voigt for partiality model, the voigt_nu parameter determines the Lorentzian and Gaussian component of the function (0.0 [Lorentzian]<= voigt_nu <= 1.0 [Gaussian]). The default value is 0.5 and will be refined in the run.
polarization_horizontal_fraction = 1.0
  .type = float
  .help = Polarization fraction in horizontal direction.
flag_output_verbose = False
  .type = bool
  .help = Output full detail of the refinement results.
flag_replace_sigI = False
  .type = bool
  .help = Replace to experimental errors I with sqrt(I).
percent_cone_fraction = 5.0
  .type = float
  .help = Perent used to select reflections inside a cone centering on each crystal axis.
isoform_name = None
  .type = str
  .help = Use this isoform.
timeout_seconds = 300
  .type = int
  .help = Time limits used for multiprocessing.
queue
  .help = "Parameters used for submitting jobs to queuing system."
{
  mode = None
    .type = str
    .help = Queing system type. Only bsub is available now.
  qname = psanaq
    .type = str
    .help = For system with queue name, specify your queue name here. For LCLS users, primary queue is the default value while high priority queue at NEH and FEH are psnehhiprioq and psfehhiprioq.
  n_nodes = 10
    .type = int
    .help = No. of nodes used.
}
"""
)

txt_help = """**************************************************************************************************

Prime: post-refinement and merging.

For more detail and citation, see Enabling X-ray free electron laser crystallography
for challenging biological systems from a limited number of crystals
"DOI: http://dx.doi.org/10.7554/eLife.05421".

Usage: prime.postrefine parameter.phil

With this command, you can specify all parameters required by prime in your parameter.phil file.
To obtain the template of these parameters, you can perform a dry run (simply run prime.postrefine).
You can then change the values of the parameters.

For feedback, please contact monarin@stanford.edu.

**************************************************************************************************

List of available parameters:
"""


def process_input(argv=None, flag_check_exist=True):
    if argv == None:
        argv = sys.argv[1:]

    user_phil = []
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):

            user_phil.append(iotbx.phil.parse(open(arg).read()))
        elif os.path.isdir(arg):
            user_phil.append(iotbx.phil.parse("""data=\"%s\"""" % arg))
        else:
            print arg
            if arg == "--help" or arg == "-h":
                print txt_help
                master_phil.show(attributes_level=1)
                exit()
            try:
                user_phil.append(iotbx.phil.parse(arg))
            except RuntimeError, e:
                raise Sorry("Unrecognized argument '%s' (error: %s)" % (arg, str(e)))

    working_phil = master_phil.fetch(sources=user_phil)
    params = working_phil.extract()

    if len(params.data) == 0:
        master_phil.show()
        raise Usage(
            "Use the above list of parameters to generate your input file (.phil). For more information, run prime.postrefine -h."
        )

    # check target_crystal_system
    crystal_system_dict = {
        "Triclinic": 0,
        "Monoclinic": 0,
        "Orthorhombic": 0,
        "Tetragonal": 0,
        "Trigonal": 0,
        "Hexagonal": 0,
        "Cubic": 0,
    }
    if params.target_crystal_system is not None:
        if params.target_crystal_system not in crystal_system_dict:
            raise Sorry(
                "Oops, incorrect target_crystal_system (available options: Triclinic, Monoclinic, Orthorhombic, Tetragonal, Trigonal, Hexagonal, or Cubic)."
            )

    # check n_residues
    if params.n_residues is None:
        raise Sorry(
            "Oops, we have a new required parameter n_residues. Please specify number of residues of your structure in asymmetric unit (n_residues = xxx)."
        )

    # check indexing ambiguity parameters
    if (
        params.indexing_ambiguity.flag_on
        and params.indexing_ambiguity.index_basis_in is None
        and params.indexing_ambiguity.assigned_basis == "h,k,l"
    ):
        raise Sorry(
            "Oops, you asked to resolve indexing ambiguity but not given any solution file nor assigned basis. \nPlease give the solution file (eg. indexing_ambiguity.index_basis_in=any.pickle/or.mtz) OR \nassigned basis (eg. indexing_ambiguity.assigned_basis=k,h,-l) OR \nturn indexing ambiguity off (eg. indexing_ambiguity.flag_on=False)."
        )
    if (
        str(params.indexing_ambiguity.index_basis_in).endswith("mtz")
        and params.indexing_ambiguity.assigned_basis == "h,k,l"
    ):
        raise Sorry(
            "Oops, you asked to resolve indexing ambiguity and gave the solution file as an mtz file. \nPlease give the assigned basis (eg. indexing_ambiguity.assigned_basis=k,h,-l) to proceed."
        )

    # generate run_no folder
    if flag_check_exist:
        if os.path.exists(params.run_no):
            raise Sorry("Oops, the run number %s already exists." % params.run_no)
        # make folders
        os.makedirs(params.run_no + "/pickles")
        os.makedirs(params.run_no + "/inputs")
        os.makedirs(params.run_no + "/mtz")
        os.makedirs(params.run_no + "/hist")
        os.makedirs(params.run_no + "/qout")
    # capture input read out by phil
    from cStringIO import StringIO

    class Capturing(list):
        def __enter__(self):
            self._stdout = sys.stdout
            sys.stdout = self._stringio = StringIO()
            return self

        def __exit__(self, *args):
            self.extend(self._stringio.getvalue().splitlines())
            sys.stdout = self._stdout

    with Capturing() as output:
        working_phil.show()

    txt_out = "prime.postrefine input:\n"
    for one_output in output:
        txt_out += one_output + "\n"

    return params, txt_out


def read_pickles(data):
    frame_files = []
    for p in data:
        if os.path.isdir(p) == False:
            if os.path.isfile(p):
                # check if list-of-pickle text file is given
                pickle_list_file = open(p, "r")
                pickle_list = pickle_list_file.read().split("\n")
            else:
                # p is a glob
                import glob

                pickle_list = glob.glob(p)
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
