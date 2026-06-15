from pathlib import Path


def process_file(filepath):
    content = Path(filepath).read_text()

    # Simple search and replace for lines starting with <<<<<<<, =======, >>>>>>>
    new_lines = []
    in_incoming = False
    for line in content.splitlines():
        if line.startswith('<<<<<<< HEAD'):
            continue
        elif line.startswith('======='):
            in_incoming = True
            continue
        elif line.startswith('>>>>>>>'):
            in_incoming = False
            continue

        if not in_incoming:
            new_lines.append(line)

    Path(filepath).write_text('\n'.join(new_lines) + '\n')

process_file('fastapi_app.py')

# Also process other files that had conflicts
files = ['portal/database.py', 'pyproject.toml', 'tests/test_booth_identity.py', 'tests/test_database.py']
for filepath in files:
    try:
        content = Path(filepath).read_text()

        new_lines = []
        in_incoming = False
        in_head = False
        for line in content.splitlines():
            if line.startswith('<<<<<<< HEAD'):
                in_head = True
                continue
            elif line.startswith('======='):
                in_head = False
                in_incoming = True
                continue
            elif line.startswith('>>>>>>>'):
                in_incoming = False
                continue

            # For these files, we want to keep what is in HEAD since we refactored the imports in HEAD
            if in_head:
                new_lines.append(line)
            elif not in_incoming:
                new_lines.append(line)

        Path(filepath).write_text('\n'.join(new_lines) + '\n')
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")
