class BlockPlanEntry:
    def __init__(self, file_path, skip=0, duration=-1):
        self.path = file_path
        self.skip = skip
        self.duration = duration

    def __str__(self):
        return f"PlanEntry: {self.path} skip={self.skip} duration={self.duration}"