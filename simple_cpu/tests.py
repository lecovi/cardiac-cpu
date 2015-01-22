import unittest, sys
sys.path.append('.')
from simple_cpu.exceptions import MemoryProtectionError
from simple_cpu.memory import UInt8, MemoryMap, MemoryController

class TestMemoryClass(unittest.TestCase):
    def setUp(self):
        self.u8 = UInt8()
        self.u8.toggle(0)
        self.u8.bit(6, True)
        self.mem = MemoryMap(0x2000)
        self.mem.write(65)
        self.mem.write16(1024)
        self.mem[0x100] = 65
        self.mem.ptr = 0x0
        self.mc = MemoryController()
        self.mc.add_map(0x0, self.mem)
        self.mc.write(65)
        self.mc.write16(1024)
        self.mc[0x100] = 65
        self.mc.ptr = 0x0
    def test_uint8(self):
        self.assertEqual(self.u8.value, 65)
        self.assertEqual(self.u8.b, 65)
        self.assertEqual(self.u8.c, 'A')
        self.assertEqual(self.u8.bit(0), True)
        self.assertEqual(self.u8.bit(1), False)
        self.assertEqual(self.u8.bit(2), False)
        self.assertEqual(self.u8.bit(3), False)
        self.assertEqual(self.u8.bit(4), False)
        self.assertEqual(self.u8.bit(5), False)
        self.assertEqual(self.u8.bit(6), True)
        self.assertEqual(self.u8.bit(7), False)
    def test_memorymap(self):
        self.mem.write_protect()
        self.assertEqual(len(self.mem), 0x2000)
        self.assertEqual(self.mem.ptr, 0x0)
        self.assertEqual(self.mem.read(), 65)
        self.assertEqual(self.mem.read16(), 1024)
        self.assertEqual(self.mem.ptr, 0x3)
        self.assertEqual(self.mem[0x100], 65)
        self.assertEqual(self.mem.ptr, 0x3)
        self.assertRaises(MemoryProtectionError, self.mem.write, [0x30, 70])
        self.mem.read_protect()
        self.assertRaises(MemoryProtectionError, self.mem.read)
    def test_memorycontroller(self):
        self.assertEqual(len(self.mc), 0xFFFF)
        self.assertEqual(self.mc.ptr, 0x0)
        self.assertEqual(self.mc.fetch(), 65)
        self.assertEqual(self.mc.fetch16(), 1024)
        self.assertEqual(self.mc.ptr, 0x3)
        self.assertEqual(self.mc[0x100], 65)
        self.assertEqual(self.mc.ptr, 0x3)

if __name__ == '__main__':
    unittest.main()
