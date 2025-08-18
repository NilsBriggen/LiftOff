import datetime
from pathlib import Path
from kdrive_client.kdrive_client import KDriveClient
from kdrive_client.kdrive_file import KDriveFile


class LiftOff:
    def __init__(self):
        self.token: str = ""
        self.drive_id: int = 0
        self.base_path: str = "/Drone Footage/"
        self.__import_credentials()
        self.remote_path = self.__get_path()

    def __import_credentials(self) -> None:
        with open("token.pw", "r") as credentials:
            lines = credentials.readlines()

        for line in lines:
            if "Token:" in line:
                self.token = line.replace("Token:", "").strip()
            elif "Drive_id:" in line:
                try:
                    self.drive_id = int(line.replace("Drive_id:", "").strip())
                except ValueError:
                    raise ValueError("Make sure your drive id is a number!")

        if self.token == "" or self.drive_id == "":
            raise Exception("Token and Drive_id are required\nPlease enter them into the token.pw file.")

    def __get_path(self) -> Path:
        return Path(self.base_path) / datetime.date.today().strftime("%Y%m%d")

    def upload(self, path: Path):
        """
        Uploads a file using KDrive.

        Parameters:\n
        - path: Path to the file or directory to upload.

        Returns:\n
        - A dictionary containing parameters and responses from KDrive API.
        """
        if self.token == "" or self.drive_id == "":
            raise Exception("Token and Drive_id are required\nPlease enter them into the token.pw file.")
        client = KDriveClient(token=self.token, drive_id=self.drive_id)

        if path.is_file():
            file = KDriveFile(str(path), str(self.remote_path))
            response = client.upload(file)
            if response["result"] != "success":
                print(f"Failed to upload {Path(file.path).name}!")
        elif path.is_dir():
            responses = []
            remote_path = str(self.remote_path)
            files = [KDriveFile(str(file_path), remote_path) for file_path in path.iterdir()]
            for file in files:
                response = client.upload(file)
                responses.append(response)
                if response["result"] != "success":
                    print(f"Failed to upload {Path(file.path).name}!")

        else:
            print(f"Failed to upload {Path(path).name}!")
