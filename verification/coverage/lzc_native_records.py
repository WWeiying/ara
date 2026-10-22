"""Strict parsing and binding of native DVE condition-vector exclusions."""
import re


def parse_records(text):
    records, checksum, scope, point_in_scope = [], None, None, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("CHECKSUM:"):
            if scope is not None and not point_in_scope:
                raise ValueError("whole-instance exclusion is not allowed")
            match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            if not match:
                raise ValueError("invalid native checksum")
            checksum, scope, point_in_scope = match.groups(), None, False
        elif line.startswith("INSTANCE:"):
            if scope is not None and not point_in_scope:
                raise ValueError("whole-instance exclusion is not allowed")
            if checksum is None:
                raise ValueError("instance without checksum")
            scope, point_in_scope = line.split(":", 1)[1].strip(), False
        elif line.startswith("ANNOTATION:"):
            if not re.fullmatch(r'ANNOTATION: "[^"\n]*"', line) or scope is None:
                raise ValueError("invalid native annotation")
        else:
            match = re.fullmatch(r'Condition (\d+) "(\d+)" "([^"\n]+) (\d+) (-?\d+)" \((\d+) "([01]+)"\)', line)
            if match is None or scope is None:
                raise ValueError("unsupported or non-vector native exclusion")
            identity, point_checksum, expression, width, bit, vector_id, vector = match.groups()
            records.append(dict(scope=scope, module_checksum=checksum[0], metric_checksum=checksum[1],
                                native_id=identity, point_checksum=point_checksum, expression=expression,
                                width=width, bit=bit, vector_id=vector_id, vector=vector))
            point_in_scope = True
    if scope is not None and not point_in_scope:
        raise ValueError("whole-instance exclusion is not allowed")
    keys = [(r["scope"], r["expression"], r["vector"]) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate native vector")
    return records


def bind_records(records, candidates):
    expected = {(c["point"]["scope"], c["point"]["expression"], c["point"]["vector"]): c
                for c in candidates}
    if len(expected) != len(candidates) or len(records) != len(candidates):
        raise ValueError("native candidate population differs")
    for record in records:
        key = record["scope"], record["expression"], record["vector"]
        if key not in expected:
            raise ValueError("unapproved native vector")
        candidate = expected.pop(key)
        point = candidate["point"]
        attrs = point["attributes"]
        wanted = dict(module_checksum=candidate["module_checksum"],
                      metric_checksum=point["metric_checksum"], native_id=point["native_id"],
                      point_checksum=attrs["chksum"], width=attrs["width"], bit="-1")
        if any(record[field] != value for field, value in wanted.items()):
            raise ValueError("native compiled signature differs")
        if record["vector"] not in candidate["structural_proof"]["unreachable_child_vectors"]:
            raise ValueError("native vector has no structural proof")
        # vector_id is captured, not inferred from the XML raw-index convention.
        if int(record["vector_id"]) < 0:
            raise ValueError("invalid captured vector identity")
    if expected:
        raise ValueError("native vectors missing")
