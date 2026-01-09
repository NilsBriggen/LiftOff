from pathlib import Path

from liftoff import LiftOff

lift_off = LiftOff()
path_to_archive = Path("place/holder")

if __name__ == "__main__":
    lift_off.archive(path_to_archive)
