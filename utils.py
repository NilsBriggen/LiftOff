class ProgressBar:
    def __init__(self, total):
        self.current = 0
        self.total = total

    def print_bar(self):
        """prints a formatted progress bar using the set *current* and *total* values"""
        percentage_done = round((self.current / self.total) * 100, 0)
        full_slots = "*" * percentage_done
        empty_slots = " " * (100-percentage_done)
        preamble = f"{current}/{total}"
        print(f"\r{preamble} |{full_slots}{empty_slots}|", end="")

    def update(self, current):
        """updates the current value of the progress bar and prints the formatted progress bar"""
        self.current = current
        self.print_bar()
        if self.current == self.total:
            print("")
