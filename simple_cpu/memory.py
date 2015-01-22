import mmap, struct, math
from simple_cpu.exceptions import MemoryProtectionError

class Unit(object):
    """
    This is the base data Unit which this CPU Virtual Machine uses to exchange data between code, memory, and disk.
    This class is meant to be sub-classed, see other Unit classes below for examples on how sub-classing works.
    """
    def __init__(self, default=0):
        self.struct = struct.Struct(self.fmt)
        self.value = default
    @property
    def value(self):
        return self._value
    @value.setter
    def value(self, value):
        """ This method controls how the value of this unit is set. This is the external API to the Unit's value that every function uses to set the value. """
        if isinstance(value, int):
            self._value = value
        elif isinstance(value, str):
            self._value = self.struct.unpack(value)[0]
        elif isinstance(value, Unit):
            self._value = value.value
        else:
            raise TypeError
    def __add__(self, other):
        if isinstance(other, int):
            return self._value + other
        elif isinstance(other, Unit):
            return self._value + other.b
        else:
            raise NotImplemented
    def __sub__(self, other):
        if isinstance(other, int):
            return self._value - other
        elif isinstance(other, Unit):
            return self._value - other.b
        else:
            raise NotImplemented
    def __eq__(self, other):
        if isinstance(other, int) and self._value == other:
            return True
        elif isinstance(other, Unit) and self._value == other.b:
            return True
        else:
            return False
    def __ne__(self, other):
        if isinstance(other, int) and self._value != other:
            return True
        elif isinstance(other, Unit) and self._value != other.b:
            return True
        else:
            return False
    def __len__(self):
        return self.struct.size
    def __str__(self):
        return self.struct.pack(self.value)
    def __int__(self):
        return self.value
    @property
    def b(self):
        """ This returns the *byte* representation of this Unit, this is an alternative to using .value property.  It is used interchangable in the code. """
        return self.value
    @property
    def c(self):
        """ This method returns the character representation of the Unit.  This is normally used to display an ACSII value to the user, or to store the data to memory or disk. """
        return self.struct.pack(self.value)
    def bit(self, offset, value=None):
        if value is None:
            return True if self._value & (1 << offset) > 0 else False
        elif value == True:
            self._value = self._value | (1 << offset)
        elif value == False:
            self._value = self._value & ~(1 << offset)
        else:
            raise ValueError('Invalid value given to bit operation.')
    def toggle(self, offset):
        self._value = self._value ^ (1 << offset)

class UInt8(Unit):
    """ This is a Unit that only supports 8-bit integers. """
    fmt = 'B'

class UInt16(Unit):
    """ This is a Unit that only supports 16-bit integers. This Unit is mostly used with memory addresses. """
    fmt = 'H'

class UInt32(Unit):
    """ This is a Unit that only supports 32-bit integers. This is not used much in the code at all, as the VM isn't really 32-bit address enabled. """
    fmt = 'L'

class MemoryMap(object):
    """ This class controls a segment of memory. """
    def __init__(self, size):
        self.mem = mmap.mmap(-1, size)
        self.size = size
        self.__read = True
        self.__write = True
        self.__execute = True
    def clear(self):
        self.mem.seek(0)
        self.mem.write('\x00' * self.size)
        self.mem.seek(0)
    def __len__(self):
        return self.size
    def __check_addr(self, addr):
        if not isinstance(addr, int):
            raise TypeError('Type %s is not valid here.' % type(addr))
        if addr < 0 or addr > self.size-1:
            raise IndexError
    def __getitem__(self, addr):
        return self.read(addr)
    def __setitem__(self, addr, byte):
        self.write(addr, byte)
    def fetch(self):
        if not self.__execute:
            raise MemoryProtectionError('Attempted to execute code from protected memory space!')
        return ord(self.mem.read(1))
    def fetch16(self):
        return self.fetch()|self.fetch()<<8
    def read(self, addr=None):
        if not self.__read:
            raise MemoryProtectionError('Attempted to read from protected memory space: %s' % addr)
        if addr is not None:
            self.__check_addr(addr)
            return ord(self.mem[addr])
        return ord(self.mem.read(1))
    def read16(self, addr=None):
        if addr is not None:
            return self.read(addr)|self.read(addr+1)<<8
        return self.read()|self.read()<<8
    def write(self, addr, byte=None):
        if not self.__write:
            raise MemoryProtectionError('Attempted to write to protected memory space: %s' % addr)
        if byte is not None:
            self.__check_addr(addr)
            if isinstance(byte, int):
                byte = chr(byte)
            self.mem[addr] = byte
        else:
            if isinstance(addr, int):
                addr = chr(addr)
            self.mem.write(addr)
    def write16(self, addr, word=None):
        if word is not None:
            self.write(addr,word&0xFF)
            self.write(addr+1,word>>8)
        else:
            self.write(addr&0xFF)
            self.write(addr>>8)
    def readblock(self, addr, size):
        self.mem.seek(addr)
        return self.mem.read(size)
    def writeblock(self, addr, block):
        self.mem.seek(addr)
        self.mem.write(block)
    def clearblock(self, addr, size):
        self.mem.seek(addr)
        self.mem.write('\x00' * size)
    def write_protect(self):
        self.__write = False
    def read_protect(self):
        self.__read = False
    @property
    def writeable(self):
        return self.__write
    @property
    def readable(self):
        return self.__read
    @property
    def ptr(self):
        return self.mem.tell()
    @ptr.setter
    def ptr(self, value):
        self.mem.seek(value)

class IOMap(object):
    """ This is the memory mapped I/O interface class, which controls access to I/O devices. """
    readable = True
    writeable = True
    def __init__(self, size=0x2000):
        self.__map = {} #: This is the memory mapping hash.
        self.__size = size
        self.__habit = 8
        self.__bitmask = 0x1ff
    def add_map(self, block, memory):
        if not getattr(memory, 'mem_read', None):
            raise
        self.__map.update({block:memory})
    @property
    def memory_map(self):
        mapping = {}
        for block, memory in self.__map.items():
            mapping.update({hex(block): [memory.readable, memory.writeable]})
        return mapping
    def __len__(self):
        return self.size
    def mem_read(self, addr):
        ha = (addr>>self.__habit)
        try:
            return self.__map[ha].mem_read(addr&self.__bitmask)
        except:
            raise
    def mem_write(self, addr, byte):
        ha = (addr>>self.__habit)
        try:
            self.__map[ha].mem_write(addr&self.__bitmask, byte)
        except:
            raise
    def readblock(self, addr, size):
        raise MemoryProtectionError('Unsupported operation by I/O map.')
    def writeblock(self, addr, block):
        raise MemoryProtectionError('Unsupported operation by I/O map.')
    def clearblock(self, addr, size):
        raise MemoryProtectionError('Unsupported operation by I/O map.')

class MemoryController(object):
    """
    This is the memory controller, which of all things controls access read/write accesses into mapped memory space.
    """
    def __init__(self, size=0xFFFF, even=True):
        self.__map = {} #: This is the memory mapping hash.
        self.__blksize = 0xE if even == True else 0xF
        self.__size = size
        self.__habit = int(math.log(size+1,2))-4
        self.__bitmask = size>>3
        self.__bank = 0x0
    @property
    def ptr(self):
        return self.__map[self.__bank].ptr
    @ptr.setter
    def ptr(self, value):
        self.__map[self.__bank].ptr = value
    @property
    def bank(self):
        return self.__bank
    @bank.setter
    def bank(self, value):
        self.__bank = value
    def add_map(self, block, memory):
        if not getattr(memory, 'read', None):
            raise
        self.__map.update({block:memory})
    @property
    def memory_map(self):
        mapping = {}
        for block, memory in self.__map.items():
            mapping.update({hex(block): [memory.readable, memory.writeable]})
        return mapping
    def __len__(self):
        return self.__size
    def fetch(self):
        return self.__map[self.__bank].fetch()
    def fetch16(self):
        return self.__map[self.__bank].fetch16()
    def read(self, addr):
        ha = (addr>>self.__habit)&self.__blksize
        try:
            return self.__map[ha].read(addr&self.__bitmask)
        except:
            raise
    def write(self, addr, byte=None):
        if byte is not None:
            if isinstance(byte, Unit):
                byte = byte.b
            ha = (addr>>self.__habit)&self.__blksize
            try:
                self.__map[ha].write(addr&self.__bitmask, byte)
            except:
                raise
        else:
            self.__map[self.__bank].write(addr)
    def __getitem__(self, addr):
        return self.read(addr)
    def __setitem__(self, addr, byte):
        self.write(addr, byte)
    def read16(self, addr):
        return self[addr]|self[addr+1]<<8
    def write16(self, addr, word=None):
        if word is not None:
            self[addr] = word&0xFF
            self[addr+1] = word>>8
        else:
            self.__map[self.__bank].write(addr&0xFF)
            self.__map[self.__bank].write(addr>>8)
    def readblock(self, addr, size):
        ha = (addr>>self.__habit)&self.__blksize
        try:
            return self.__map[ha].readblock(addr&self.__bitmask, size)
        except:
            raise
    def writeblock(self, addr, block):
        ha = (addr>>self.__habit)&self.__blksize
        try:
            self.__map[ha].writeblock(addr&self.__bitmask, block)
        except:
            raise
    def memcopy(self, src, dest, size):
        ha_src = (src>>self.__habit)&self.__blksize
        ha_dst = (dest>>self.__habit)&self.__blksize
        try:
            buf = self.__map[ha_src].readblock(src&self.__bitmask, size)
        except:
            raise
        try:
            self.__map[ha_dst].writeblock(dest&self.__bitmask, buf)
        except:
            raise
    def memmove(self, src, dest, size):
        ha = (src>>self.__habit)&self.__blksize
        self.memcopy(src, dest, size)
        self.__map[ha].clearblock(dest&self.__bitmask, size)
    