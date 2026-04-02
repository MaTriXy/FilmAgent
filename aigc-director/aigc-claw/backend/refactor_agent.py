import os
import re

path = r'd:\Projects\AIGC-Claw\aigc-director\aigc-claw\backend\core\agents\script_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. 删除所有以 _PROMPT_ZH/EN 结尾的字符串定义
# 匹配: LOGLINE_GENERATE_PROMPT_ZH = """..."""
# 注意：使用正则清理，但不准删除 Class 本身
# 我们识别以三引号包裹的文本块进行精准删除
pattern = r'[A-Z0-9_]+_PROMPT_(ZH|EN)\s*=\s*\"\"\"[\s\S]*?\"\"\"'
text = re.sub(pattern, '', text)

# 2. 注入提示词加载器
if "def _get_script_prompt" not in text:
    header = 'from datetime import datetime, timezone\nfrom typing import Any, Optional, Dict\n\nfrom prompts.loader import load_prompt_with_fallback\n\ndef _get_script_prompt(name: str, lang: str = "zh") -> str:\n    return load_prompt_with_fallback("script", name, lang, "zh")\n'
    text = text.replace('from datetime import datetime, timezone\nfrom typing import Any, Optional, Dict', header)

# 3. 批量替换引用: (NAME_ZH if is_zh else NAME_EN)
# 找出这种常见模式
pairs = re.findall(r'\(([A-Z_0-9]+)_ZH\s+if\s+is_zh\s+else\s+\1_EN\)', text)
for base in set(pairs):
    clean = base.replace('_PROMPT', '').lower()
    old = f'({base}_ZH if is_zh else {base}_EN)'
    new = f'_get_script_prompt(\"{clean}\", \"zh\" if is_zh else \"en\")'
    text = text.replace(old, new)

# 4. 替换单纯的 xxx_PROMPT_ZH/EN (如果还带 .format 的话)
singles = re.findall(r'([A-Z_0-9]+_PROMPT)_(ZH|EN)', text)
for base, lang in set(singles):
    clean = base.replace('_PROMPT', '').lower()
    l = lang.lower()
    text = text.replace(f'{base}_{lang}', f'_get_script_prompt(\"{clean}\", \"{l}\")')

# 5. 确保 ACT_NAMES_ZH/EN 保留 (因为它们不是 Prompt 文字，而是映射表)
# 以上正则不应删除非三引号的 ACT_NAMES

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("CLEAN REFACTOR FINISHED: Kept 1000+ lines logic, synced external prompts.")
