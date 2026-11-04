import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tasks'))
os.environ['OPENAI_API_BASE'] = 'https://example.invalid/v1'
os.environ['OPENAI_API_KEY'] = 'unit-test-secret-do-not-print'
os.environ['MPLBACKEND'] = 'Agg'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['NLTK_DATA'] = str(ROOT / '.cache' / 'nltk_data')

