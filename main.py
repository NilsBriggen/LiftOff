from liftoff import LiftOff

lift_off = LiftOff()
path_to_upload = Path("place/holder")

if __name__ == "__main__":
    lift_off.upload(path_to_upload)