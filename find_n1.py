import ast
import os

def find_loops_with_await(path):
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    try:
                        tree = ast.parse(f.read(), filename=filepath)
                    except:
                        continue

                    for node in ast.walk(tree):
                        if isinstance(node, (ast.For, ast.AsyncFor)):
                            for subnode in ast.walk(node):
                                if isinstance(subnode, ast.Await):
                                    print(f"File {filepath}, Line {node.lineno}: Loop contains await")
                                    break
find_loops_with_await('portal/')
