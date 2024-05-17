from wappler.utils.log import get_logger

logger = get_logger(__name__)


class LightWatch:

    def __init__(self) -> None:
        self.charcount = 0

    def count(self, text_throughput: str) -> None:
        self.charcount += len(str(text_throughput))

    def report(self) -> int:
        return self.charcount
