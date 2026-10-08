"""Exercise actual exporter functions without requiring Blender for pure ABI checks."""
import ast
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np

source=Path(__file__).resolve().parents[1]/'tlou_extractor/blender_vita_export.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and
           node.name in ('quantize_batch_positions','write_batch','oct_normal','kd_batches')]
namespace={'np':np,'hashlib':hashlib,'struct':struct,'VERTEX':struct.Struct('<4B3h2e2b')}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),namespace)
quantize=namespace['quantize_batch_positions']
write_batch=namespace['write_batch']


class QuantizationTests(unittest.TestCase):
    def test_shared_vertices_with_different_batch_centres(self):
        shared=np.asarray([[4.123,29.296,-28.233],[7.049,34.033,-33.985]],dtype=np.float32)
        first=np.vstack([shared,[-3.837,22.354,-40.736]])
        second=np.vstack([shared,[18.497,37.476,-20.937]])
        # Demonstrate the old independent grids really produced different seam positions.
        def old(points):
            centre=(points.min(axis=0)+points.max(axis=0))*.5
            return np.rint((points-centre)*100)*.01+centre
        self.assertGreater(np.max(np.abs(old(first)[:2]-old(second)[:2])),.001)
        a,oa=quantize(first);b,ob=quantize(second)
        # Exact integer world coordinates match, irrespective of floating-point decoding.
        np.testing.assert_array_equal(a[:2]+np.rint(oa*100).astype(np.int64),
                                      b[:2]+np.rint(ob*100).astype(np.int64))

    def test_world_ties_independent_of_origin_parity(self):
        shared=np.array([[.125,-.125,1.125]])
        a,oa=quantize(np.vstack([shared,[0,0,0]]))
        b,ob=quantize(np.vstack([shared,[.03,.03,.03]]))
        np.testing.assert_array_equal(a[0]+np.rint(oa*100).astype(np.int64),[12,-12,112])
        np.testing.assert_array_equal(b[0]+np.rint(ob*100).astype(np.int64),[12,-12,112])

    def test_negative_positions_and_error_bound(self):
        rng=np.random.default_rng(123)
        points=rng.uniform(-150,150,(500,3)).astype(np.float32)
        local,origin=quantize(points)
        self.assertLessEqual(np.max(np.abs(local*.01+origin-points)),.005000001)
        self.assertTrue(np.all(local>=-32768) and np.all(local<=32767))
        np.testing.assert_allclose(origin*100,np.rint(origin*100),atol=1e-10)

    def test_asymmetric_full_int16_range(self):
        local,origin=quantize([[0,0,0],[655.35,0,0]])
        self.assertEqual(int(local[:,0].min()),-32768)
        self.assertEqual(int(local[:,0].max()),32767)
        with self.assertRaises(ValueError):quantize([[0,0,0],[655.36,0,0]])
        for points in ([],[[float('nan'),0,0]],[[float('inf'),0,0]]):
            with self.assertRaises(ValueError):quantize(points)

    def test_real_packed_batches_keep_stride_attributes_and_bounds(self):
        shared=[4.123,29.296,-28.233]
        all_instances=[];decoded=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'assets/models').mkdir(parents=True)
            for extra in ([-3.837,22.354,-40.736],[18.497,37.476,-20.937]):
                rows=np.asarray([shared+[0,1,0,.25,.75,.2,.4,.6,1],
                                 extra+[0,1,0,0,0,.2,.4,.6,1],
                                 [7.049,34.033,-33.985]+[0,1,0,1,1,.2,.4,.6,1]],dtype=np.float32)
                report={'clipped_color_corners':0}
                write_batch(rows,'texture.bin',root,all_instances,1,report)
                matrix,low,high,model,texture=all_instances[-1]
                blob=(root/model.removeprefix('app0:/')).read_bytes()
                self.assertEqual(len(blob),4+3*16)
                vertex=struct.unpack_from('<4B3h2e2b',blob,4)
                self.assertEqual(vertex[:4],(51,102,153,255))
                self.assertEqual(vertex[7:9],(.25,.75))
                # Model translations are serialized as float32; emulate engine arithmetic.
                origin=np.asarray(matrix[12:15],dtype=np.float32)
                positions=np.asarray(vertex[4:7],dtype=np.float32)*np.float32(.01)+origin
                decoded.append(positions)
                self.assertTrue(np.all(positions>=low) and np.all(positions<=high))
                self.assertEqual(texture,'texture.bin')
            np.testing.assert_allclose(decoded[0],decoded[1],rtol=0,atol=1e-5)
            self.assertEqual(len(all_instances),2) # no extra draw batches

if __name__=='__main__':unittest.main()
