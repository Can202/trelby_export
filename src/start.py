

import sys

# The following line is modified at installation time by setup.py so it
# points to the actual modules installation path.
sys.path.insert(0, "src")

import trelby
trelby.main()
