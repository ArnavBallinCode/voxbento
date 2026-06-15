import re
from pathlib import Path


def process_file(filepath):
    content = Path(filepath).read_text()

    # We are trying to keep the HEAD version, which corresponds to the refactored imports at the top
    # The incoming branch has imports inline.
    # The format is
    # <<<<<<< HEAD
    # =======
    #     some imports
    # >>>>>>> a8ae599...

    pattern = re.compile(r'<<<<<<< HEAD\n=======\n(?:(?:[ \t]+from portal\..+\n)|(?:[ \t]+import .+\n)|(?:[ \t]+.+\n))*?>>>>>>> [a-f0-9]+\n', re.MULTILINE)

    new_content = re.sub(pattern, '', content)

    Path(filepath).write_text(new_content)

process_file('fastapi_app.py')
