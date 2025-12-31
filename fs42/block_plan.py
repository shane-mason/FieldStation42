class BlockPlanEntry:
    def __init__(self, the_path, skip=0, duration=-1, is_stream=False, content_type="feature", media_type="video"):
        self.path = the_path
        self.skip = skip
        self.duration = duration
        self.is_stream = is_stream
        self.content_type = content_type
        self.media_type = media_type

    def toJSON(self):
        return {"path": self.path, "skip": self.skip, "duration": self.duration, "is_stream": self.is_stream, "content_type": self.content_type, "media_type": self.media_type}

    def __str__(self):
        return f"PlanEntry: {self.path} skip={self.skip} duration={self.duration}"
