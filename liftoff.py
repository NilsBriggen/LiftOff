import datetime
from pathlib import Path

from utils import Error, ProgressBar


class LiftOff:
    def __init__(self):
        self.base_path: str = "/Drone Footage/"
        self.archive_path = self.__get_path()
        self.last_error = None

    def __get_path(self) -> Path:
        return Path(self.base_path) / datetime.date.today().strftime("%Y%m%d")

    def __rename_single(self, input_path: Path) -> bool | Exception:
        try:
            new_name = self.archive_path / input_path.name
            input_path.rename(new_name)
            return True
        except (FileNotFoundError, PermissionError, OSError) as e:
            self.last_error = e
            return False


    def archive(self, input_path: Path):
        """
        Archives a file to a designated folder.

        Parameters:\n
        - input_path: Path to the file or directory to archive.
        """
        if input_path.is_file():
            if not self.__rename_single(input_path):
                print(f"\rAn error occured while archiving {input_path}: {self.last_error}")
            else:
                print(f"\r{input_path} was successfully archived.")
        elif input_path.is_dir():
            file_list = [file for file in input_path.rglob("*")]
            if not file_list:
                print(f"\rNo files could be found in {input_path}")
            progress_bar = ProgressBar(len(file_list))
            for i, file in enumerate(file_list):
                if not self.__rename_single(file):
                    print(f"\rAn error occured while archiving {file}: {self.last_error}")
                else:
                    print(f"\r{file} was successfully archived.")
                progress_bar.update(i+1)
        else:
            print(f"Failed to upload {Path(input_path).name}!")
