#!/usr/bin/env python3
"""Minimal ISO-BMFF tool: `describe <file>` prints tracks/codec/bit depth/colour/stts;
`duppts <src> <dst>` rewrites the video stts so frame pairs (40,41) (80,81) (100,101)
share one timestamp (duplicate PTS; no ctts in the source, so PTS == DTS)."""
import json, struct, sys

CONTAINERS = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'edts', b'udta'}

def boxes(buf, start, end):
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack('>I4s', buf[pos:pos + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack('>Q', buf[pos + 8:pos + 16])[0]; hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr or pos + size > end:
            return
        yield pos, size, hdr, kind
        pos += size

def find(buf, start, end, path):
    """Yield (pos,size,hdr,chain) for every box whose kind == path[-1] under the path."""
    for pos, size, hdr, kind in boxes(buf, start, end):
        if kind == path[0]:
            if len(path) == 1:
                yield pos, size, hdr, [(pos, size, hdr)]
            elif kind in CONTAINERS:
                for p in find(buf, pos + hdr, pos + size, path[1:]):
                    yield p[0], p[1], p[2], [(pos, size, hdr)] + p[3]

def track_info(buf, tpos, tsize, thdr):
    info = {}
    for pos, size, hdr, _ in find(buf, tpos + thdr, tpos + tsize, [b'mdia', b'hdlr']):
        info['handler'] = buf[pos + hdr + 8:pos + hdr + 12].decode('latin1')
    for pos, size, hdr, _ in find(buf, tpos + thdr, tpos + tsize, [b'mdia', b'mdhd']):
        v = buf[pos + hdr]
        info['timescale'] = struct.unpack('>I', buf[pos + hdr + (20 if v == 1 else 12):][:4])[0]
    for pos, size, hdr, _ in find(buf, tpos + thdr, tpos + tsize, [b'mdia', b'minf', b'stbl', b'stsd']):
        e = pos + hdr + 8
        info['codec'] = buf[e + 4:e + 8].decode('latin1')
        ent = buf[e:e + struct.unpack('>I', buf[e:e + 4])[0]]
        i = ent.find(b'hvcC')
        if i > 0:   # hvcC: bitDepthLumaMinus8 is payload byte 17 (low 3 bits)
            info['bit_depth'] = (ent[i + 4 + 17] & 7) + 8
        j = ent.find(b'colr')
        if j > 0 and ent[j + 4:j + 8] in (b'nclx', b'nclc'):
            p, t, m = struct.unpack('>HHH', ent[j + 8:j + 14])
            info['colour'] = {'primaries': p, 'transfer': t, 'matrix': m}
    for pos, size, hdr, _ in find(buf, tpos + thdr, tpos + tsize, [b'mdia', b'minf', b'stbl', b'stts']):
        n = struct.unpack('>I', buf[pos + hdr + 4:pos + hdr + 8])[0]
        ents = [struct.unpack('>II', buf[pos + hdr + 8 + 8 * k:pos + hdr + 16 + 8 * k]) for k in range(n)]
        info['samples'] = sum(c for c, _ in ents)
        info['stts'] = ents if n <= 12 else ents[:6] + [('...', n - 12)] + ents[-6:]
    info['ctts'] = any(True for _ in find(buf, tpos + thdr, tpos + tsize, [b'mdia', b'minf', b'stbl', b'ctts']))
    return info

def describe(path):
    buf = open(path, 'rb').read()
    out = {'file': path.split('/')[-1], 'bytes': len(buf), 'tracks': []}
    for tpos, tsize, thdr, _ in find(buf, 0, len(buf), [b'moov', b'trak']):
        out['tracks'].append(track_info(buf, tpos, tsize, thdr))
    return out

DUP_PAIRS = ((40, 41), (80, 81), (100, 101))

def duppts(src, dst):
    buf = bytearray(open(src, 'rb').read())
    for tpos, tsize, thdr, tchain in find(buf, 0, len(buf), [b'moov', b'trak']):
        if track_info(buf, tpos, tsize, thdr).get('handler') != 'vide':
            continue
        (pos, size, hdr, chain), = list(find(buf, tpos + thdr, tpos + tsize, [b'mdia', b'minf', b'stbl', b'stts']))
        n = struct.unpack('>I', buf[pos + hdr + 4:pos + hdr + 8])[0]
        deltas = []
        for k in range(n):
            c, d = struct.unpack('>II', buf[pos + hdr + 8 + 8 * k:pos + hdr + 16 + 8 * k]); deltas += [d] * c
        for a, _ in DUP_PAIRS:         # sample a+1 gets a's timestamp; later frames keep theirs
            deltas[a + 1] += deltas[a]; deltas[a] = 0
        ents = []
        for d in deltas:
            if ents and ents[-1][1] == d: ents[-1][0] += 1
            else: ents.append([1, d])
        body = buf[pos + hdr:pos + hdr + 4] + struct.pack('>I', len(ents)) + b''.join(struct.pack('>II', c, d) for c, d in ents)
        new = struct.pack('>I4s', 8 + len(body), b'stts') + body
        grow = len(new) - size
        moov_pos = tchain[0][0]
        for cpos, csize, chdr in tchain + chain[:-1]:      # moov, trak, mdia, minf, stbl
            assert chdr == 8, 'large-size parent boxes not supported'
            struct.pack_into('>I', buf, cpos, csize + grow)
        buf[pos:pos + size] = new
        mdat_after = any(k == b'mdat' and p > moov_pos for p, _, _, k in boxes(buf, 0, len(buf)))
        if grow and mdat_after:        # chunk offsets point past the grown moov
            for sp, ss, sh, _ in find(buf, 0, len(buf), [b'moov', b'trak', b'mdia', b'minf', b'stbl', b'stco']):
                m = struct.unpack('>I', buf[sp + sh + 4:sp + sh + 8])[0]
                for k in range(m):
                    o = sp + sh + 8 + 4 * k
                    struct.pack_into('>I', buf, o, struct.unpack('>I', buf[o:o + 4])[0] + grow)
            assert not any(True for _ in find(buf, 0, len(buf), [b'moov', b'trak', b'mdia', b'minf', b'stbl', b'co64']))
        open(dst, 'wb').write(buf)
        return len(deltas)
    raise SystemExit('no video track')

if __name__ == '__main__':
    if sys.argv[1] == 'describe':
        for p in sys.argv[2:]: print(json.dumps(describe(p)))
    elif sys.argv[1] == 'duppts':
        print('frames', duppts(sys.argv[2], sys.argv[3]))
