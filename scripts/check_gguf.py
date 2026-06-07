#!/usr/bin/env python3
"""Quick GGUF metadata inspector — checks architecture and tensor names."""

import struct
import sys
import json

GGUF_MAGIC = 0x46554747  # 'GGUF' in little-endian (bytes: 47 47 55 46)

def read_string(f):
    length = struct.unpack('<Q', f.read(8))[0]
    return f.read(length).decode('utf-8', errors='replace')

def read_value(f, vtype):
    if vtype == 0:   # UINT8
        return struct.unpack('<B', f.read(1))[0]
    elif vtype == 1: # INT8
        return struct.unpack('<b', f.read(1))[0]
    elif vtype == 2: # UINT16
        return struct.unpack('<H', f.read(2))[0]
    elif vtype == 3: # INT16
        return struct.unpack('<h', f.read(2))[0]
    elif vtype == 4: # UINT32
        return struct.unpack('<I', f.read(4))[0]
    elif vtype == 5: # INT32
        return struct.unpack('<i', f.read(4))[0]
    elif vtype == 6: # FLOAT32
        return struct.unpack('<f', f.read(4))[0]
    elif vtype == 7: # BOOL
        return struct.unpack('<?', f.read(1))[0]
    elif vtype == 8: # STRING
        return read_string(f)
    elif vtype == 9: # ARRAY
        arr_type = struct.unpack('<I', f.read(4))[0]
        arr_len = struct.unpack('<Q', f.read(8))[0]
        return [read_value(f, arr_type) for _ in range(arr_len)]
    elif vtype == 10: # UINT64
        return struct.unpack('<Q', f.read(8))[0]
    elif vtype == 11: # INT64
        return struct.unpack('<q', f.read(8))[0]
    elif vtype == 12: # FLOAT64
        return struct.unpack('<d', f.read(8))[0]
    else:
        raise ValueError(f"Unknown type: {vtype}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_gguf.py <model.gguf>")
        sys.exit(1)
    
    path = sys.argv[1]
    print(f"Inspecting: {path}\n")
    
    with open(path, 'rb') as f:
        # Header
        magic = struct.unpack('<I', f.read(4))[0]
        if magic != GGUF_MAGIC:
            print(f"ERROR: Not a GGUF file (magic=0x{magic:08x})")
            sys.exit(1)
        
        version = struct.unpack('<I', f.read(4))[0]
        n_tensors = struct.unpack('<Q', f.read(8))[0]
        n_metadata = struct.unpack('<Q', f.read(8))[0]
        
        print(f"GGUF Version : {version}")
        print(f"Tensors      : {n_tensors}")
        print(f"Metadata KVs : {n_metadata}\n")
        
        # Read metadata
        print("=" * 60)
        print("METADATA (first 50 KVs)")
        print("=" * 60)
        
        key_metadata = {}
        for i in range(n_metadata):
            key = read_string(f)
            vtype = struct.unpack('<I', f.read(4))[0]
            value = read_value(f, vtype)
            key_metadata[key] = value
            
            # Print important keys
            if any(x in key.lower() for x in ['arch', 'name', 'type', 'model', 'general']):
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                print(f"  {key}: {value}")
        
        print()
        
        # Extract key info
        arch = key_metadata.get('general.architecture', 'unknown')
        name = key_metadata.get('general.name', 'unknown')
        print(f"Architecture : {arch}")
        print(f"Model Name   : {name}")
        
        # Read tensor info
        print()
        print("=" * 60)
        print(f"TENSOR NAMES (first 20 of {n_tensors})")
        print("=" * 60)
        
        tensor_names = []
        for i in range(min(20, n_tensors)):
            tname = read_string(f)
            n_dims = struct.unpack('<I', f.read(4))[0]
            dims = [struct.unpack('<Q', f.read(8))[0] for _ in range(n_dims)]
            dtype = struct.unpack('<I', f.read(4))[0]
            offset = struct.unpack('<Q', f.read(8))[0]
            tensor_names.append(tname)
            print(f"  {tname}  shape={dims}  dtype={dtype}")
        
        # Check for expected tensors
        print()
        print("=" * 60)
        print("TENSOR CHECK")
        print("=" * 60)
        
        expected = ['blk.0.attn_q.weight', 'blk.0.attn_k.weight', 'blk.0.attn_v.weight']
        for t in expected:
            found = any(t in name for name in tensor_names)
            status = "FOUND" if found else "MISSING"
            print(f"  {t}: {status}")
        
        # Also check qwen3 naming
        print()
        print("Checking alternate naming patterns...")
        qwen2_patterns = ['blk.0.attn_q.weight', 'blk.0.attn_norm.weight']
        for p in qwen2_patterns:
            found = any(p in name for name in tensor_names)
            print(f"  {p}: {'FOUND' if found else 'NOT FOUND'}")

if __name__ == '__main__':
    main()
