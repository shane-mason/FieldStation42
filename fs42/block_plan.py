class BlockPlanEntry:
    def __init__(self, the_path, skip=0, duration=-1, is_stream=False):
        self.path = the_path
        self.skip = skip
        self.duration = duration
        self.is_stream = is_stream

    def toJSON(self):
        return {"path": self.path, "skip": self.skip, "duration": self.duration, "is_stream": self.is_stream}

    def __str__(self):
        return f"PlanEntry: {self.path} skip={self.skip} duration={self.duration}"
