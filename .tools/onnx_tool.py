# -*- coding: utf-8 -*-
"""极简 ONNX protobuf 读写：不做完整 schema 校验，只按已知字段号导航/改图。
用途：给内嵌 PP-OCR rec 模型追加"GPU 端 argmax"节点，把 [B,T,6625] fp32 回读降为 [B,T] 索引。
用法:
  python onnx_tool.py inspect <model.onnx>
  python onnx_tool.py edit <in.onnx> <out.onnx> [--mode fp16|argmax]
"""
import sys, struct

# ---------- protobuf 基础读写 ----------
def read_varint(b, i):
    v = 0; s = 0
    while True:
        x = b[i]; i += 1
        v |= (x & 0x7f) << s
        if not (x & 0x80):
            return v, i
        s += 7


def write_varint(v):
    out = bytearray()
    while True:
        x = v & 0x7f
        v >>= 7
        if v:
            out.append(x | 0x80)
        else:
            out.append(x)
            return bytes(out)


def parse_fields(b):
    """返回 [(field_no, wire, raw_bytes_or_int)]；wire=0 varint, 2 length-delimited, 5 fixed32, 1 fixed64"""
    out = []
    i = 0
    n = len(b)
    while i < n:
        key, i = read_varint(b, i)
        fno, wire = key >> 3, key & 7
        if wire == 0:
            v, i = read_varint(b, i)
            out.append((fno, wire, v))
        elif wire == 2:
            ln, i = read_varint(b, i)
            out.append((fno, wire, b[i:i + ln]))
            i += ln
        elif wire == 5:
            out.append((fno, wire, b[i:i + 4])); i += 4
        elif wire == 1:
            out.append((fno, wire, b[i:i + 8])); i += 8
        else:
            raise ValueError('wire %d' % wire)
    return out


def ser_field(fno, wire, val):
    key = write_varint((fno << 3) | wire)
    if wire == 0:
        return key + write_varint(val)
    if wire == 2:
        return key + write_varint(len(val)) + val
    return key + val


def enc_str(fno, s):
    return ser_field(fno, 2, s.encode('utf-8') if isinstance(s, str) else s)


def enc_msg(fno, payload):
    return ser_field(fno, 2, payload)


def enc_int(fno, v):
    return ser_field(fno, 0, v)


# ---------- ONNX 结构导航 ----------
MODEL_GRAPH = 7   # ModelProto.graph（ir_version=1, producer_name=2, ..., graph=7, opset_import=8）
G_NODE, G_NAME, G_INIT, G_DOC, G_INPUT, G_OUTPUT, G_VINFO = 1, 2, 5, 10, 11, 12, 13
N_IN, N_OUT, N_NAME, N_OP, N_ATTR, N_DOC, N_DOMAIN = 1, 2, 3, 4, 5, 6, 7
A_NAME, A_F, A_I, A_INTS, A_TYPE = 1, 2, 3, 8, 20
T_DIMS, T_DTYPE, T_FLOAT, T_INT32, T_STR, T_INT64, T_NAME, T_RAW = 1, 2, 4, 5, 6, 7, 8, 9
V_NAME, V_TYPE = 1, 2
TY_TENSOR = 1
TT_ELEM, TT_SHAPE = 1, 2
TS_DIM = 1
DIM_VAL, DIM_PARAM = 1, 2

DT = {'float32': 1, 'uint8': 2, 'int8': 3, 'int32': 6, 'int64': 7, 'bool': 9, 'float16': 10}


def node(op, ins, outs, name, attrs=None):
    b = b''.join(enc_str(N_IN, s) for s in ins)
    b += b''.join(enc_str(N_OUT, s) for s in outs)
    b += enc_str(N_NAME, name)
    b += enc_str(N_OP, op)
    for a in (attrs or []):
        b += enc_msg(N_ATTR, a)
    return b


def attr_i(name, v):
    return enc_str(A_NAME, name) + enc_int(A_I, v) + enc_int(A_TYPE, 2)


def attr_ints(name, vs):
    b = enc_str(A_NAME, name) + b''.join(enc_int(A_INTS, v) for v in vs)
    return b + enc_int(A_TYPE, 7)


def tensor_f32(name, dims, values):
    b = b''.join(enc_int(T_DIMS, d) for d in dims)
    b += enc_int(T_DTYPE, DT['float32'])
    b += enc_str(T_NAME, name)
    b += enc_msg(T_RAW, struct.pack('<%df' % len(values), *values))
    return b


def tensor_i64(name, dims, values):
    b = b''.join(enc_int(T_DIMS, d) for d in dims)
    b += enc_int(T_DTYPE, DT['int64'])
    b += enc_str(T_NAME, name)
    b += enc_msg(T_RAW, b''.join(struct.pack('<q', v) for v in values))
    return b


def value_info(name, elem_type, dims):
    """dims: 整数或字符串（动态维）"""
    dimb = b''
    for d in dims:
        dimb += enc_msg(TS_DIM, enc_int(DIM_VAL, d) if isinstance(d, int) else enc_str(DIM_PARAM, d))
    shape = enc_msg(TT_SHAPE, dimb)
    tt = enc_int(TT_ELEM, elem_type) + shape
    return enc_str(V_NAME, name) + enc_msg(V_TYPE, enc_msg(TY_TENSOR, tt))


class Model:
    def __init__(self, data):
        self.top = parse_fields(data)
        graphs = [v for (f, w, v) in self.top if f == MODEL_GRAPH]
        if len(graphs) != 1:
            raise ValueError('graph field not found')
        self.graph = parse_fields(graphs[0])

    def g(self, fno):
        return [v for (f, w, v) in self.graph if f == fno]

    def nodes(self):
        return [parse_fields(v) for v in self.g(G_NODE)]

    def op_types(self):
        out = []
        for nd in self.nodes():
            op = [v for (f, w, v) in nd if f == N_OP]
            out.append(op[0].decode() if op else '?')
        return out

    def inputs(self):
        return [parse_fields(v) for v in self.g(G_INPUT)]

    def outputs(self):
        return [parse_fields(v) for v in self.g(G_OUTPUT)]

    def rebuild(self, extra_nodes=(), extra_inits=(), extra_outputs=(), drop_outputs=()):
        """重建顶层 ModelProto：graph 内追加节点/初始化器/输出，可删除指定输出名"""
        gb = b''
        for (f, w, v) in self.graph:
            if f == G_OUTPUT and drop_outputs:
                nm = [xx for (ff, ww, xx) in parse_fields(v) if ff == V_NAME]
                if nm and nm[0].decode() in drop_outputs:
                    continue
            if f == G_NODE:
                gb += enc_msg(G_NODE, v)
            elif f == G_INIT:
                gb += enc_msg(G_INIT, v)
            elif f == G_OUTPUT:
                gb += enc_msg(G_OUTPUT, v)
            else:
                gb += ser_field(f, w, v)
        for n in extra_nodes:
            gb += enc_msg(G_NODE, n)
        for i in extra_inits:
            gb += enc_msg(G_INIT, i)
        for o in extra_outputs:
            gb += enc_msg(G_OUTPUT, o)
        top = b''
        for (f, w, v) in self.top:
            if f == MODEL_GRAPH:
                top += enc_msg(MODEL_GRAPH, gb)
            else:
                top += ser_field(f, w, v)
        return top


def cmd_inspect(path):
    data = open(path, 'rb').read()
    m = Model(data)
    print('bytes:', len(data))
    print('ops:', m.op_types()[:8], '...', m.op_types()[-6:])
    print('op count:', len(m.op_types()))
    from collections import Counter
    print('op histogram:', Counter(m.op_types()).most_common(20))
    print('inputs:')
    for vi in m.inputs():
        nm = [v for (f, w, v) in vi if f == V_NAME]
        ty = [v for (f, w, v) in vi if f == V_TYPE]
        dims = []
        if ty:
            t1 = [v for (f, w, v) in parse_fields(ty[0]) if f == TY_TENSOR]
            if t1:
                f1 = parse_fields(t1[0])
                elem = [v for (f, w, v) in f1 if f == TT_ELEM]
                sh = [v for (f, w, v) in f1 if f == TT_SHAPE]
                if sh:
                    for d in parse_fields(sh[0]):
                        dd = parse_fields(d)
                        for (f, w, v) in dd:
                            dims.append(v if f == DIM_VAL else ('?' + v.decode()))
                print('  ', nm[0].decode() if nm else '?', 'elem=', elem[0] if elem else '?', 'dims=', dims)
    print('outputs:')
    for vi in m.outputs():
        nm = [v for (f, w, v) in vi if f == V_NAME]
        print('  ', nm[0].decode() if nm else '?')
    print('initializers:', len(m.g(G_INIT)))
    return m


def cmd_build(src, dst, mode):
    """在 rec 模型末尾追加节点，把输出从 [B,T,6625] 概率改成小张量。
    mode:
      fp16         -> Cast 到 float16（回读减半）
      argmax       -> ArgMax(axis=2)  -> [B,T] int64（回读降 6625 倍，依赖 WebGPU int64 支持）
      argmax_float -> ReduceMax + Equal + Cast + MatMul 常量索引 -> [B,T] float32（全浮点链路）
      argmax_i32   -> ArgMax + Cast(int32)
    """
    data = open(src, 'rb').read()
    m = Model(data)
    out_name = None
    for vi in m.outputs():
        nm = [v for (f, w, v) in vi if f == V_NAME]
        if nm:
            out_name = nm[0].decode()
    if not out_name:
        raise SystemExit('no graph output')
    extra_nodes, extra_inits, extra_out = [], [], []
    if mode == 'fp16':
        extra_nodes.append(node('Cast', [out_name], ['out_f16'], 'Cast_f16', [attr_i('to', DT['float16'])]))
        extra_out.append(value_info('out_f16', DT['float16'], ['batch', 'seq', 'classes']))
        drop = {out_name}
    elif mode == 'argmax':
        extra_nodes.append(node('ArgMax', [out_name], ['out_idx'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 0)]))
        extra_out.append(value_info('out_idx', DT['int64'], ['batch', 'seq']))
        drop = {out_name}
    elif mode == 'argmax_i32':
        extra_nodes.append(node('ArgMax', [out_name], ['idx64'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 0)]))
        extra_nodes.append(node('Cast', ['idx64'], ['out_idx'], 'Cast_i32', [attr_i('to', DT['int32'])]))
        extra_out.append(value_info('out_idx', DT['int32'], ['batch', 'seq']))
        drop = {out_name}
    elif mode in ('rmax_pre', 'am2_pre'):
        # 在 Softmax 之前的 logits 上做规约：用于隔离 Softmax 本身的耗时
        # （argmax 对单调变换不变，故索引与在原概率上一致；最大 logit 不等于概率，仅作诊断）
        src = 'p2o.pd_op.add.100.0'
        if mode == 'rmax_pre':
            extra_nodes.append(node('ReduceMax', [src], ['out_idx'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 0)]))
            extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq']))
        else:
            extra_nodes.append(node('ArgMax', [src], ['idx64'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 1)]))
            extra_nodes.append(node('Cast', ['idx64'], ['idxf'], 'Cast_f32', [attr_i('to', DT['float32'])]))
            extra_nodes.append(node('ReduceMax', [src], ['maxv'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 1)]))
            extra_nodes.append(node('Concat', ['idxf', 'maxv'], ['out_idx'], 'Concat_idx', [attr_i('axis', 2)]))
            extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq', 2]))
        drop = {out_name}
    elif mode in ('cast16', 'rmax', 'am1', 'am2_f16'):
        # 诊断/优化变体：分别隔离 Cast / ReduceMax / ArgMax 的开销
        if mode == 'cast16':
            extra_nodes.append(node('Cast', [out_name], ['out_idx'], 'Cast_f16', [attr_i('to', DT['float16'])]))
            extra_out.append(value_info('out_idx', DT['float16'], ['batch', 'seq', 'classes']))
        elif mode == 'rmax':
            extra_nodes.append(node('ReduceMax', [out_name], ['out_idx'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 0)]))
            extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq']))
        elif mode == 'am1':
            extra_nodes.append(node('ArgMax', [out_name], ['idx64'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 0)]))
            extra_nodes.append(node('Cast', ['idx64'], ['out_idx'], 'Cast_f32', [attr_i('to', DT['float32'])]))
            extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq']))
        else:  # am2_f16：先在 fp16 空间做 argmax/最大值，减半规约访存
            extra_nodes.append(node('Cast', [out_name], ['x16'], 'Cast_f16', [attr_i('to', DT['float16'])]))
            extra_nodes.append(node('ArgMax', ['x16'], ['idx64'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 1)]))
            extra_nodes.append(node('Cast', ['idx64'], ['idxf'], 'Cast_f32', [attr_i('to', DT['float32'])]))
            extra_nodes.append(node('ReduceMax', ['x16'], ['maxv16'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 1)]))
            extra_nodes.append(node('Cast', ['maxv16'], ['maxv'], 'Cast_f32b', [attr_i('to', DT['float32'])]))
            extra_nodes.append(node('Concat', ['idxf', 'maxv'], ['out_idx'], 'Concat_idx', [attr_i('axis', 2)]))
            extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq', 2]))
        drop = {out_name}
    elif mode in ('argmax2', 'argmax2_i32'):
        # 输出 [B,T,2]：第 0 通道 = argmax 索引，第 1 通道 = 该处最大概率（供 confidence 过滤）
        if mode == 'argmax2':
            extra_nodes.append(node('ArgMax', [out_name], ['idx64'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 1)]))
        else:
            extra_nodes.append(node('ArgMax', [out_name], ['idx64'], 'ArgMax_2', [attr_i('axis', 2), attr_i('keepdims', 1)]))
            extra_nodes.append(node('Cast', ['idx64'], ['idx32'], 'Cast_i32', [attr_i('to', DT['int32'])]))
        src_idx = 'idx32' if mode == 'argmax2_i32' else 'idx64'
        extra_nodes.append(node('Cast', [src_idx], ['idxf'], 'Cast_f32', [attr_i('to', DT['float32'])]))
        extra_nodes.append(node('ReduceMax', [out_name], ['maxv'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 1)]))
        extra_nodes.append(node('Concat', ['idxf', 'maxv'], ['out_idx'], 'Concat_idx', [attr_i('axis', 2)]))
        extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq', 2]))
        drop = {out_name}
    elif mode == 'equal_float':
        # opset>=11 的纯浮点链路：ReduceMax -> Equal -> Cast -> MatMul(常量索引) -> Concat
        C = int(__import__('os').environ.get('REC_CLASSES', '18385'))
        extra_nodes.append(node('ReduceMax', [out_name], ['maxv'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 1)]))
        extra_nodes.append(node('Equal', [out_name, 'maxv'], ['eqmask'], 'Equal_max', []))
        extra_nodes.append(node('Cast', ['eqmask'], ['eqf'], 'Cast_f32', [attr_i('to', DT['float32'])]))
        extra_inits.append(tensor_f32('idx_const', [C, 1], [float(i) for i in range(C)]))
        extra_nodes.append(node('MatMul', ['eqf', 'idx_const'], ['idx_f'], 'MatMul_idx', []))
        extra_nodes.append(node('Concat', ['idx_f', 'maxv'], ['out_idx'], 'Concat_idx', [attr_i('axis', 2)]))
        extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq', 2]))
        drop = {out_name}
    elif mode == 'argmax_float':
        # C（类别数）从 Softmax 输出维推断：由调用方通过环境变量或默认 6625 提供
        C = int(__import__('os').environ.get('REC_CLASSES', '6625'))
        extra_nodes.append(node('ReduceMax', [out_name], ['maxv'], 'ReduceMax_2', [attr_ints('axes', [2]), attr_i('keepdims', 1)]))
        extra_nodes.append(node('Equal', [out_name, 'maxv'], ['eqmask'], 'Equal_max', []))
        extra_nodes.append(node('Cast', ['eqmask'], ['eqf'], 'Cast_f32', [attr_i('to', DT['float32'])]))
        extra_inits.append(tensor_f32('idx_const', [C, 1], [float(i) for i in range(C)]))
        extra_nodes.append(node('MatMul', ['eqf', 'idx_const'], ['idx_f'], 'MatMul_idx', []))
        extra_nodes.append(node('Squeeze', ['idx_f'], ['out_idx'], 'Squeeze_idx', [attr_ints('axes', [2])]))
        extra_out.append(value_info('out_idx', DT['float32'], ['batch', 'seq']))
        drop = {out_name}
    else:
        raise SystemExit('unknown mode ' + mode)
    out = m.rebuild(extra_nodes=extra_nodes, extra_inits=extra_inits,
                    extra_outputs=extra_out, drop_outputs=drop)
    open(dst, 'wb').write(out)
    print('wrote %s (%d bytes, mode=%s, dropped output %s)' % (dst, len(out), mode, out_name))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    if sys.argv[1] == 'inspect':
        cmd_inspect(sys.argv[2])
    elif sys.argv[1] == 'build':
        cmd_build(sys.argv[2], sys.argv[3], sys.argv[4])

