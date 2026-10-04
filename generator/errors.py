"""Exceptions shared by the pipeline driver and the outline loop."""


class SoftReject(ValueError):
    """A validator complaint worth one retry but not worth stopping the
    run: if the retry is still rejected for it, the answer is accepted and
    whatever is wrong is left to the checks downstream (for the premise
    repair, the next audit round; for a line plan, a note in the story
    document). A saved answer it would reject is never reported as stale."""


class PipelineHalt(RuntimeError):
    """Raised when a verify/repair loop exhausts its rounds with a hard
    finding still standing, or a story directory was written by an older
    schema. The pipeline stops rather than building on material it knows is
    broken; the message names the files."""
