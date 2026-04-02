import os
import re

path = r'd:\Projects\AIGC-Claw\aigc-director\aigc-claw\backend\core\agents\script_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Fix the broken variable assignments
bad_patterns = [
    r'_get_script_prompt\([^)]+\)\s*=\s*\([\s\S]*?\n\)\n', # _get_script_prompt(...) = (\n...\n)
    r'MICRO__get_script_prompt\([^)]+\)\s*=\s*\([\s\S]*?\n\)\n',
]
for p in bad_patterns:
    text = re.sub(p, '', text)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("Removed broken assignment definitions.")
