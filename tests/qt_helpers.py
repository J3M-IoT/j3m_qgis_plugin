"""Bounded waits which dispatch Qt events and let Python worker tasks run."""
import time
from qgis.core import QgsApplication


def wait_for(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while not predicate():
        QgsApplication.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError('Qt operation did not finish within timeout')
        time.sleep(.005)
    QgsApplication.processEvents()
