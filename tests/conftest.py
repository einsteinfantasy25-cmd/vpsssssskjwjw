import os

# Ensure the module can import with safe defaults during tests.
os.environ.setdefault("BOTS_JSON", "[]")
os.environ.setdefault("ENABLE_RUNNER", "false")
os.environ.setdefault("ENABLE_TERMINAL", "false")
