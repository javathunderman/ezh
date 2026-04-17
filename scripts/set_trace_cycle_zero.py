import os

def normalize_trace_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    first_cycle = None
    parsed = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            parsed.append(("raw", line))
            continue

        parts = stripped.split()

        if len(parts) != 3:
            parsed.append(("raw", line))
            continue

        addr, cmd, cycle_str = parts

        try:
            cycle = int(cycle_str)
        except ValueError:
            parsed.append(("raw", line))
            continue

        if first_cycle is None:
            first_cycle = cycle

        parsed.append(("entry", addr, cmd, cycle))

    if first_cycle is None:
        return

    out_lines = []

    for item in parsed:
        if item[0] == "raw":
            out_lines.append(item[1].rstrip())
        else:
            _, addr, cmd, cycle = item
            new_cycle = cycle - first_cycle
            out_lines.append(f"{addr} {cmd} {new_cycle}")

    with open(filepath, 'w') as f:
        f.write("\n".join(out_lines) + "\n")


def main():
    root = ""
    for r, _, files in os.walk(root):
        for file in files:
            if file.endswith(".trace") or file.endswith(".txt"):
                normalize_trace_file(os.path.join(r, file))


if __name__ == "__main__":
    main()