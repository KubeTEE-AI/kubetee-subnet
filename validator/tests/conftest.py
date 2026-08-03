import os
import sys

# The validator directory is a flat unit of bare-import modules, not a
# package; put it on sys.path so tests can `import config`, etc.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
