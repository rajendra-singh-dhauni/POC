import os
import subprocess
from pathlib import Path
from tree_sitter import Language, Parser

GRAMMAR_LIB = Path('.cgr') / 'build' / 'my-languages.so'
VENDOR = Path('vendor')
TS_DART_REPO = VENDOR / 'tree-sitter-dart'

class DartTreeParser:
    def __init__(self):
        self.lib_path = GRAMMAR_LIB
        self.language = None
        self.parser = None

    def ensure_grammar_built(self) -> None:
        if self.lib_path.exists():
            return
        # create vendor dir
        VENDOR.mkdir(exist_ok=True)
        # clone if needed
        if not TS_DART_REPO.exists():
            print('Cloning tree-sitter-dart grammar...')
            subprocess.check_call(['git','clone','https://github.com/tree-sitter/tree-sitter-dart', str(TS_DART_REPO)])
        # build library
        self.lib_path.parent.mkdir(parents=True, exist_ok=True)
        print('Building Tree-sitter Dart grammar (requires cmake and a C toolchain)...')
        Language.build_library(
            str(self.lib_path),
            [str(TS_DART_REPO)]
        )

    def _ensure_parser(self):
        if self.parser is not None:
            return
        if not self.lib_path.exists():
            raise RuntimeError('Grammar library not found; run ensure_grammar_built()')
        lang = Language(str(self.lib_path), 'dart')
        self.language = lang
        p = Parser()
        p.set_language(lang)
        self.parser = p

    def parse_file(self, path: Path):
        self._ensure_parser()
        data = path.read_bytes()
        tree = self.parser.parse(data)
        return tree.root_node, 'dart'

    def extract_functions(self, root, path: Path):
        # return list of dict: {name, start_line, end_line}
        funcs = []
        source = path.read_bytes()
        stack = [root]
        while stack:
            node = stack.pop()
            # Tree-sitter dart top-level functions are often 'function_declaration'
            if node.type in ('function_declaration', 'function_definition'):
                name_node = None
                for ch in node.children:
                    if ch.type == 'identifier':
                        name_node = ch
                        break
                if name_node is None:
                    # some grammar variants put name under 'name'
                    name_node = node.named_child(0) if node.named_child_count > 0 else None
                name = source[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='ignore') if name_node is not None else f"<anon_fn_{node.start_point[0]+1}>"
                funcs.append({'name': name, 'start_line': node.start_point[0]+1, 'end_line': node.end_point[0]+1})
            # also handle method declarations inside classes
            if node.type == 'method_declaration':
                name_node = None
                for ch in node.children:
                    if ch.type == 'identifier':
                        name_node = ch
                        break
                name = source[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='ignore') if name_node is not None else f"<anon_m_{node.start_point[0]+1}>"
                funcs.append({'name': name, 'start_line': node.start_point[0]+1, 'end_line': node.end_point[0]+1})
            stack.extend(child for child in node.children)
        return funcs

    def extract_classes(self, root, path: Path):
        classes = []
        source = path.read_bytes()
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == 'class_declaration':
                # children often include 'name' or identifier
                name_node = None
                for ch in node.children:
                    if ch.type == 'identifier' or ch.type == 'name':
                        name_node = ch
                        break
                name = source[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='ignore') if name_node is not None else f"<anon_class_{node.start_point[0]+1}>"
                classes.append({'name': name, 'start_line': node.start_point[0]+1, 'end_line': node.end_point[0]+1})
            stack.extend(child for child in node.children)
        return classes

    def extract_calls(self, root, path: Path):
        calls = []
        source = path.read_bytes()
        stack = [root]
        while stack:
            node = stack.pop()
            # dart method invocations can be 'method_invocation' or 'invocation_expression' or 'function_invocation' or 'call_expression'
            if node.type in ('method_invocation', 'invocation_expression', 'function_invocation', 'call_expression'):
                # try to find identifier child
                ident = None
                for ch in node.children:
                    if ch.type == 'identifier':
                        ident = ch
                        break
                    # method_invocation can have a 'member' or 'property' child
                if ident is None:
                    # deep search for identifier
                    stack2 = list(node.children)
                    while stack2 and ident is None:
                        n = stack2.pop()
                        if n.type == 'identifier':
                            ident = n
                            break
                        stack2.extend(n.children)
                if ident is not None:
                    name = source[ident.start_byte:ident.end_byte].decode('utf-8', errors='ignore')
                    calls.append({'name': name, 'start_line': node.start_point[0]+1})
            stack.extend(child for child in node.children)
        return calls

    def extract_imports(self, path: Path):
        imports = []
        try:
            text = path.read_text(encoding='utf-8')
        except Exception:
            return imports
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('import '):
                parts = line.split()
                if len(parts) >= 2:
                    target = parts[1].strip().strip('"').strip("'")
                    imports.append(target)
        return imports
