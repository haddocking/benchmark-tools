import argparse
import logging
import sys
import time
from haddock_benchmark_tools.version import version

from haddock_benchmark_tools.modules.configuration import ConfigFile
from haddock_benchmark_tools.modules.haddock import HaddockWrapper, HaddockJob
from haddock_benchmark_tools.modules.dataset import Dataset

setuplog = logging.getLogger("setuplog")
ch = logging.StreamHandler()
formatter = logging.Formatter(
    " %(asctime)s %(module)s:%(lineno)d %(levelname)s - %(message)s"
)
ch.setFormatter(formatter)
setuplog.addHandler(ch)


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    # https://stackoverflow.com/a/312464
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def init(config_file):
    """Initialize the Setup script and do the validations."""
    setuplog.info("Initializing Setup")

    # Configuration
    setuplog.info("Reading configuration file")
    conf = ConfigFile(config_file)

    try:
        setuplog.info("Validating configuration file")
        conf.validate()
    except Exception as e:
        setuplog.error(e)
        sys.exit()

    setuplog.info("Configuration file OK")

    # Dataset
    setuplog.info("Loading Dataset")
    dataset = Dataset(dataset_path=conf.dataset_path)

    try:
        setuplog.info("Checking if receptor and ligands match suffix")
        dataset.check_input_files(
            receptor_suffix=conf.receptor_suffix, ligand_suffix=conf.ligand_suffix
        )
    except Exception as e:
        setuplog.error(e)
        sys.exit()

    setuplog.info("Input files are OK")

    # Haddock
    setuplog.info("Initializing HADDOCK Wrapper")
    haddock = HaddockWrapper(haddock_path=conf.haddock_path, py2=conf.py2_path)

    try:
        setuplog.info("Checking if HADDOCK is executable")
        haddock.check_if_executable()
    except Exception as e:
        setuplog.error(e)
        sys.exit()

    setuplog.info("HADDOCK execution OK")

    # All checks ok!
    setuplog.info("Initialization done!")
    return conf, dataset, haddock


# Command line interface parser
ap = argparse.ArgumentParser()


ap = argparse.ArgumentParser(description="Run a Haddock Benchmark")
ap.add_argument("config_file", help="Configuration file, toml format")
ap.add_argument(
    "--force",
    dest="force",
    action="store_true",
    default=False,
    help="DEV only, forcefully removeinitiated runs",
)

ap.add_argument(
    "-v",
    "--version",
    help="show version",
    action="version",
    version=f"Running {ap.prog} v{version}",
)


def load_args(ap):
    """Load argument parser args."""
    return ap.parse_args()


def cli(ap, main):
    """Command-line interface entry point."""
    cmd = load_args(ap)
    main(**vars(cmd))


def maincli():
    """Execute main client."""
    cli(ap, main)


def main(config_file, force=False, log_level="INFO"):
    setuplog.setLevel(log_level)
    setuplog.info("###############################################")
    setuplog.info("")
    setuplog.info(f"      Welcome to benchmark-tools v{version}")
    setuplog.info("")
    setuplog.info("###############################################")
    setuplog.warning(
        "If this is not running in the background, your "
        "benchmarking will stop when you close the terminal!"
    )
    setuplog.warning(
        f"To run it in the background, run with: "
        f'"nohup python {" ".join(sys.argv)} &"'
    )
    time.sleep(10)

    config, dataset, haddock = init(config_file)

    prepared_run_l = []
    for i, run_scenario in enumerate(config.scenarios):
        setuplog.info(f"Setting up Scenario {i+1}")
        setuplog.info(run_scenario)
        ready_runs = dataset.setup(
            haddock=haddock,
            parameters=run_scenario,
            receptor_suffix=config.receptor_suffix,
            ligand_suffix=config.ligand_suffix,
            force=force,
        )
        prepared_run_l.extend(ready_runs)

    setuplog.info("Generating Job list")
    job_list = []
    for target in prepared_run_l:
        job = HaddockJob(
            haddock_path=config.haddock_path, py2=config.py2_path, run_path=target
        )
        job_list.append(job)

    # Execute!
    # TODO: change submission logic to continous mode
    concurrent_jobs = 10
    counter = 1
    total_jobs = len(job_list)
    setuplog.info(f"Executing jobs n={total_jobs}")
    complete = False
    while not complete:

        for i, job_subset in enumerate(chunks(job_list, concurrent_jobs)):
            setuplog.info(f"Running job subset {i+1}")

            subset_complete = False
            while not subset_complete:

                status_list = []
                for job in job_subset:

                    job.update_status()

                    status_list.append(job.status)

                    if job.status == "null":
                        setuplog.info(f"Starting job {counter}/{total_jobs} {job.path}")
                        job.run()
                        counter += 1

                    elif job.status == "failed":
                        setuplog.warning(f"Failed {job.path}")

                    elif job.status == "running":
                        setuplog.info(f"Running {job.path}")

                    elif job.status == "complete":
                        setuplog.info(f"Complete {job.path}")

                total_complete = status_list.count("complete")
                total_failed = status_list.count("failed")

                if total_complete + total_failed == len(job_subset):
                    # all complete or failed
                    setuplog.info("Subset complete")
                    subset_complete = True

                else:
                    setuplog.info("Waiting...")
                    time.sleep(600)

        complete = True


if __name__ == "__main__":
    sys.exit(maincli())
