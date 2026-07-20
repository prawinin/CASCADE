import os
import re

emoji_pattern = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    "\u2702-\u27b0"          # Dingbats
    "\u24c2-\U0001f251"
    ""
    "]+", flags=re.UNICODE)

comment_header_pattern = re.compile(r'#\s*+\s*(.*?)\s**$')

for root, dirs, files in os.walk("."):
    if ".git" in root or ".venv" in root or "node_modules" in root or "__pycache__" in root or "brain" in root:
        continue
    for file in files:
        if file.endswith(('.py', '.js', '.html', '.sh')):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                new_content = emoji_pattern.sub('', content)
                
                # For python, replace "#  text " with "# text"
                lines = new_content.split('\n')
                for i, line in enumerate(lines):
                    if line.strip().startswith('#'):
                        match = comment_header_pattern.search(line)
                        if match:
                            # Extract leading whitespace
                            indent = line[:len(line) - len(line.lstrip())]
                            lines[i] = f"{indent}# {match.group(1).strip()}"
                
                new_content = '\n'.join(lines)
                
                if new_content != content:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Cleaned {path}")
            except Exception as e:
                print(f"Error {path}: {e}")
