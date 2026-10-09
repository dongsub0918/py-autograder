"""Inspect *how* a submission computed something, not just the value it ended up with.

Works on the parsed AST of the statements that were run, so comments, docstrings
(the notebook's instructions) and commented-out code never count.

    src.code_of("x_fixed")   -> "np.arange(1, 6)"      (last top-level assignment)
    src.calls("x_fixed")     -> {"numpy.arange"}       (import aliases resolved)
    src.fstring_fields("both")   -> ["x", "Y"]         (code inside each {...})
    src.hardcoded_fields("both") -> ["5", "17"]        (fields that use no variable)
"""

import ast


def _dotted(node):
    """`np.random.rand` -> "np.random.rand"; None for anything that isn't a plain name chain."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _assigned_names(stmt):
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        targets = [stmt.target]
    else:
        return set()
    return {t.id for t in targets if isinstance(t, ast.Name)}


class Source:
    def __init__(self, statements):
        self.statements = statements
        self.aliases = {}  # local name -> full module path, from every import in the file
        for node in (n for stmt in statements for n in ast.walk(stmt)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        self.aliases[a.asname] = a.name
                    else:  # `import numpy.linalg` binds `numpy`
                        top = a.name.split(".")[0]
                        self.aliases[top] = top
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    self.aliases[a.asname or a.name] = f"{node.module}.{a.name}"

    def _last_assignment(self, name, before=None):
        """Index of the last top-level statement assigning `name` (before index `before`)."""
        end = len(self.statements) if before is None else before
        for i in range(end - 1, -1, -1):
            if name in _assigned_names(self.statements[i]):
                return i
        return None

    def code_of(self, name):
        """Source of the right-hand side of the last top-level assignment to `name`, or None."""
        i = self._last_assignment(name)
        return None if i is None else ast.unparse(self.statements[i].value)

    def resolve(self, dotted):
        """"np.arange" -> "numpy.arange" using the file's imports."""
        head, _, rest = dotted.partition(".")
        full = self.aliases.get(head, head)
        return f"{full}.{rest}" if rest else full

    def calls(self, name, follow=1):
        """Functions called in the last top-level assignment to `name`, with import aliases
        resolved. Also includes calls from variables it uses, `follow` levels deep, so
        `r = np.arange(1, 6); x_fixed = r` still reports numpy.arange."""
        i = self._last_assignment(name)
        return set() if i is None else self._calls_at(i, follow)

    def fstring_fields(self, name):
        """Code inside each {...} of the f-string assigned to `name`, e.g. ["x", "Y"].
        None if `name` isn't assigned an f-string. Follows `name = other_var` one level."""
        i = self._last_assignment(name)
        if i is None:
            return None
        value = self.statements[i].value
        if isinstance(value, ast.Name):
            j = self._last_assignment(value.id, before=i)
            value = None if j is None else self.statements[j].value
        if not isinstance(value, ast.JoinedStr):
            return None
        return [ast.unparse(v.value) for v in value.values if isinstance(v, ast.FormattedValue)]

    def hardcoded_fields(self, name):
        """The {...} fields of `name`'s f-string that don't use any variable, e.g. ["5", "17"]
        for f"x = {5}, Y = {17}". Empty when every field reads a variable."""
        fields = self.fstring_fields(name) or []
        return [f for f in fields
                if not any(isinstance(n, ast.Name) for n in ast.walk(ast.parse(f, mode="eval")))]

    def _calls_at(self, i, follow):
        value = self.statements[i].value
        found = set()
        for node in ast.walk(value):
            if isinstance(node, ast.Call) and (dotted := _dotted(node.func)):
                found.add(self.resolve(dotted))
            elif follow > 0 and isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                j = self._last_assignment(node.id, before=i)
                if j is not None:
                    found |= self._calls_at(j, follow - 1)
        return found
