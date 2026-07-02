import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("boss_analyzer")


class BaseScraper(ABC):

    def __init__(self):
        self.logger = logging.getLogger(f"boss_analyzer.{self.__class__.__name__}")

    @abstractmethod
    def scrape(self, query: str) -> dict:
        raise NotImplementedError
