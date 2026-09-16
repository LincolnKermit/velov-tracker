import os
import sys

# Ensure repository root is on sys.path for serverless imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app

# Export `app` for Vercel WSGI handler
