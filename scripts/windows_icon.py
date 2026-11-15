"""Replace PE icon resources without requiring a Windows build machine.

The existing executable code is unchanged. A new read-only resource section
contains the original resources plus the supplied ICO. The derivative executable
is unsigned; this does not retain or imply Python's publisher signature.
"""

import struct
from pathlib import Path


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def read_resources(data):
    pe = struct.unpack_from("<I", data, 60)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    if struct.unpack_from("<H", data, optional)[0] != 0x20B:
        raise ValueError("Expected a 64-bit Windows executable")
    table = optional + optional_size
    sections = []
    for index in range(count):
        sections.append(struct.unpack_from("<8sIIII", data, table + index * 40))

    def offset(rva):
        for _, size, address, raw_size, raw_offset in sections:
            if address <= rva < address + max(size, raw_size):
                return raw_offset + rva - address
        raise ValueError("Resource address outside executable sections")

    resource_rva = struct.unpack_from("<I", data, optional + 112 + 16)[0]
    base = offset(resource_rva)

    def parse(relative):
        start = base + relative
        named, ids = struct.unpack_from("<HH", data, start + 12)
        result = {}
        for index in range(named + ids):
            name, target = struct.unpack_from("<II", data, start + 16 + index * 8)
            if name & 0x80000000:
                position = base + (name & 0x7FFFFFFF)
                length = struct.unpack_from("<H", data, position)[0]
                name = data[position + 2:position + 2 + length * 2].decode("utf-16-le")
            if target & 0x80000000:
                result[name] = parse(target & 0x7FFFFFFF)
            else:
                rva, size, codepage, _ = struct.unpack_from("<IIII", data, base + target)
                result[name] = (bytes(data[offset(rva):offset(rva) + size]), codepage)
        return result

    return parse(0), (pe, optional, table, sections)


def encode_resources(tree, rva):
    output = bytearray()

    def reserve(size):
        position = len(output)
        output.extend(b"\0" * size)
        return position

    def emit(node):
        keys = sorted(node, key=lambda key: (not isinstance(key, str), key))
        position = reserve(16 + 8 * len(keys))
        named = sum(isinstance(key, str) for key in keys)
        struct.pack_into("<HH", output, position + 12, named, len(keys) - named)
        for index, key in enumerate(keys):
            name = key
            if isinstance(key, str):
                encoded = key.encode("utf-16-le")
                name = reserve(2 + len(encoded))
                struct.pack_into("<H", output, name, len(encoded) // 2)
                output[name + 2:name + 2 + len(encoded)] = encoded
                name |= 0x80000000
            value = node[key]
            if isinstance(value, dict):
                target = emit(value) | 0x80000000
            else:
                payload, codepage = value
                reserve((-len(output)) % 4)
                target = reserve(16)
                location = reserve(len(payload))
                output[location:location + len(payload)] = payload
                struct.pack_into("<IIII", output, target, rva + location, len(payload), codepage, 0)
            struct.pack_into("<II", output, position + 16 + 8 * index, name, target)
        return position

    emit(tree)
    return output


def replace_icon(executable, icon_path):
    data = bytearray(Path(executable).read_bytes())
    tree, (pe, optional, table, sections) = read_resources(data)
    icon = Path(icon_path).read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", icon)
    if reserved != 0 or kind != 1:
        raise ValueError("Expected a valid ICO file")
    group = bytearray(struct.pack("<HHH", 0, 1, count))
    tree[3] = {}
    for index in range(count):
        entry = icon[6 + index * 16:22 + index * 16]
        width, height, colors, zero, planes, bits, size, start = struct.unpack("<BBBBHHII", entry)
        resource_id = index + 1
        tree[3][resource_id] = {1033: (icon[start:start + size], 0)}
        group.extend(struct.pack("<BBBBHHIH", width, height, colors, zero, planes, bits, size, resource_id))
    tree[14] = {1: {1033: (bytes(group), 0)}}
    file_alignment = struct.unpack_from("<I", data, optional + 36)[0]
    section_alignment = struct.unpack_from("<I", data, optional + 32)[0]
    first_raw = min(section[4] for section in sections if section[4])
    if table + (len(sections) + 1) * 40 > first_raw:
        raise ValueError("Executable has no space for another section header")
    rva = align(max(section[2] + max(section[1], section[3]) for section in sections), section_alignment)
    resources = encode_resources(tree, rva)
    raw_offset = align(len(data), file_alignment)
    raw_size = align(len(resources), file_alignment)
    data.extend(b"\0" * (raw_offset + raw_size - len(data)))
    data[raw_offset:raw_offset + len(resources)] = resources
    struct.pack_into("<8sIIIIIIHHI", data, table + len(sections) * 40,
                     b".mscres\0", len(resources), rva, raw_size, raw_offset, 0, 0, 0, 0, 0x40000040)
    struct.pack_into("<H", data, pe + 6, len(sections) + 1)
    struct.pack_into("<I", data, optional + 56, align(rva + len(resources), section_alignment))
    initialized = struct.unpack_from("<I", data, optional + 8)[0]
    struct.pack_into("<I", data, optional + 8, initialized + raw_size)
    struct.pack_into("<I", data, optional + 64, 0)
    struct.pack_into("<II", data, optional + 112 + 16, rva, len(resources))
    struct.pack_into("<II", data, optional + 112 + 32, 0, 0)
    parsed, _ = read_resources(data)
    if parsed != tree:
        raise ValueError("Icon replacement failed resource verification")
    Path(executable).write_bytes(data)
