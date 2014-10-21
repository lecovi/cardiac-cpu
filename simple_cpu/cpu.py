import sys, zlib, mmap, struct, math
from simple_cpu.exceptions import MemoryProtectionError, CPUException
from simple_cpu.devices import ConIOHook, HelloWorldHook

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
    def fetch(self):
        if not self.__execute:
            raise MemoryProtectionError('Attempted to execute code from protected memory space!')
        return ord(self.mem.read(1))
    def mem_read(self, addr=None):
        if not self.__read:
            raise MemoryProtectionError('Attempted to read from protected memory space: %s' % addr)
        if addr is not None:
            self.__check_addr(addr)
            return ord(self.mem[addr])
        return ord(self.mem.read(1))
    def mem_write(self, addr, byte=None):
        if not self.__write:
            raise MemoryProtectionError('Attempted to write to protected memory space: %s' % addr)
        if byte:
            self.__check_addr(addr)
            if isinstance(byte, int):
                byte = chr(byte)
            self.mem[addr] = byte
        else:
            if isinstance(addr, int):
                addr = chr(addr)
            self.mem.write(addr)
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
        return self.__size
    def fetch(self):
        return self.__map[self.__bank].fetch()
    def fetch16(self):
        return self.__map[self.__bank].fetch()|self.__map[self.__bank].fetch()<<8
    def read(self, addr):
        ha = (addr>>self.__habit)&self.__blksize
        try:
            return self.__map[ha].mem_read(addr&self.__bitmask)
        except:
            raise
    def write(self, addr, byte=None):
        if byte is not None:
            if isinstance(byte, Unit):
                byte = byte.b
            ha = (addr>>self.__habit)&self.__blksize
            try:
                self.__map[ha].mem_write(addr&self.__bitmask, byte)
            except:
                raise
        else:
            self.__map[self.__bank].mem_write(addr)
    def __getitem__(self, addr):
        return self.read(addr)
    def __setitem__(self, addr, byte):
        self.write(addr, byte)
    def read16(self, addr):
        return self[addr]|self[addr+1]<<8
    def write16(self, addr, word=None):
        if word:
            self[addr] = word&0xFF
            self[addr+1] = word>>8
        else:
            self.__map[self.__bank].mem_write(addr&0xFF)
            self.__map[self.__bank].mem_write(addr>>8)
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

class CPURegisters(object):
    """ This class contains all the CPU registers and manages them. """
    registers = ['ip','ax','bx','cx','dx','sp','bp','si','di','cs','ds','es','ss','cr']
    pushable = ['ip','ax','bx','cx','dx','si','di','cs','ds','es']
    def __init__(self):
        for reg in self.registers:
            setattr(self, reg, UInt16())

class CPU(object):
    """
    This class is the core CPU/Virtual Machine class.  It has most of the runtime that should be platform independent.
    This class does not contain any code that can touch the host operating environment, so it cannot load or save data.
    Depending on how or where you want the binary data/memory to be located in the host environment, let it be on disk, or in a database,
    you will need to subclass this and enable your specific environment's functionality.
    The other class below this CPU, should work on most operating systems to access standard disk and memory.
    """
    def __init__(self):
        self.regs = CPURegisters()
        self.flags = UInt8()
        self.mem = MemoryController()
        self.iomap = IOMap()
        self.mem.add_map(0x0, MemoryMap(0x2000))
        self.mem.add_map(0xa, self.iomap)
        self.cpu_hooks = {}
        self.devices = []
        self.__opcodes = {}
        for name in dir(self.__class__):
            if name[:7] == 'opcode_':
                self.__opcodes.update({int(name[7:], 16):getattr(self, name)})
    @property
    def var_map(self):
        return self.regs.registers
    def __getattr__(self, name):
        if name in self.regs.registers:
            return getattr(self.regs, name)
        raise AttributeError("%s isn't here." % name)
    def add_device(self, klass):
        hook = klass(self)
        self.devices.append(hook)
        for port in hook.ports:
            self.cpu_hooks.update({port: hook})
        if hasattr(hook, 'io_address'):
            self.iomap.add_map(hook.io_address, hook)
    def clear_registers(self, persistent=[]):
        for reg in self.regs.registers:
            if reg not in persistent:
                getattr(self.regs, reg).value = 0
    def push_registers(self, regs=None):
        if regs is None:
            regs = self.regs.pushable
        for reg in regs:
            self.mem[self.ss+self.sp] = getattr(self.regs, reg)
            self.sp.value += 2
    def pop_registers(self, regs=None):
        if regs is None:
            regs = self.regs.pushable.reverse()
        for reg in regs:
            self.sp.value -= 2
            getattr(self.regs, reg).value = self.mem[self.ss+self.sp:self.ss+self.sp+2]
    def push_value(self, value):
        try:
            value = int(value)
            self.mem[self.ss+self.sp] = value
            self.sp.value += 2
        except:
            self.mem.ptr = self.ds
            self.mem.write(value+chr(0))
            self.mem[self.ss+self.sp] = 0
            self.sp.value += 2
    def pop_value(self):
        if self.sp.value > 0:
            self.sp.value -= 2
            return self.mem[self.ss+self.sp:self.ss+self.sp+2]
        raise CPUException('Stack out of range.')
    def get_xop(self, dst=None, errmsg='Internal value error.'):
        """ This handy function to translate the xop code and return a proper integer from the source. """
        xop = self.mem.read()
        if dst is not None:
            if not xop.bit(dst):
                raise CPUException(errmsg)
        xop_map = {1:'<HH', # MEM,IMED
                   2:'<BH', # REG,IMED
                   5:'<HH', # MEM,MEM
                   6:'<BH', # REG,MEM
                   9:'<HB', # MEM,REG
                   10:'<BB' # REG,REG
        }
        dst,src = struct.unpack(xop_map[xop.b], self.mem.read(struct.calcsize(xop_map[xop.b])))
        if xop.bit(3):
            # Register is source.
            src = getattr(self, self.var_map[src]).b
        elif xop.bit(2):
            # Memory address is the source.
            src = self.mem[self.ds.b+src].b
        return xop,dst,src
    def get_value(self, resolve=True):
        b = self.fetch()
        typ = b>>4
        b = b&0xf
        if typ == 0:
            value = getattr(self, self.var_map[b])
        elif typ == 1:
            value = b
        elif typ in (2,4,5,):
            value = b|self.fetch()<<4
        elif typ == 3:
            value = b|self.fetch16()<<4
        if resolve:
            if typ == 0:
                value = value.b
            elif typ == 4:
                value = self.mem.read(value)
            elif typ == 5:
                value = self.mem.read16(value)
        return typ, value
    def device_command(self, cmd):
        for device in self.devices:
            handler = getattr(device, cmd, None)
            if handler:
                handler()
    def start_devices(self):
        self.device_command('start')
    def stop_devices(self):
        self.device_command('stop')
    def device_cycle(self):
        self.device_command('cycle')
    def fetch(self):
        return self.mem.fetch()
    def fetch16(self):
        return self.mem.fetch16()
    def process(self):
        """ Processes a single bytecode. """
        self.mem.ptr = self.cs+self.ip
        op = self.fetch()
        if self.__opcodes.has_key(op):
            if not self.__opcodes[op]():
                self.ip.value = self.mem.ptr-self.cs.b
        else:
            raise CPUException('Invalid OpCode detected: %s' % op)
    def opcode_0x0(self):
        pass # NOP
    def opcode_0x1(self):
        i = self.fetch()
        if i > 0:
            self.ip.value = self.mem.ptr-self.cs
            self.push_registers(['cs', 'ip'])
            jmp = self.mem[i*2+self.int_table:i*2+self.int_table+2]
            self.regs.cs.value = jmp
            self.ip.value = 0
        else:
            self.pop_registers(['ip', 'cs'])
        return True
    def opcode_0x2(self):
        src = self.get_value()[1]
        typ, dst = self.get_value(False)
        print src,typ,dst
        if typ == 0:
            dst.value = src
        elif typ == 4:
            self.mem[self.ds+dst] = src
        elif typ == 5:
            self.mem.write16(self.ds+dst, src)
        else:
            raise CPUException('Attempted to move data into immediate value.')
    def opcode_0x3(self):
        src = self.get_value()[1]
        typ, v = self.get_value()
        port = self.mem.read16().b
        if self.cpu_hooks.has_key(port):
            getattr(self, self.var_map[v]).value = self.cpu_hooks[port].input(port)
    def opcode_0x5(self):
        self.running = False
    def run(self, cs=0, persistent=[]):
        self.clear_registers(persistent)
        self.cs.value = cs
        self.mem.ptr = 0
        del persistent
        del cs
        self.running = True
        while self.running:
            if 'bp' in self.__dict__ and self.bp == self.mem.ptr: break
            self.process()
        return 0
    def run_old(self, cs=0, persistent=[]):
        """
        This method is where all the magic happens, and where bytecode execution starts.
        You can optionally pass a custom code segment to start at, and what registers shouldn't be cleared before execution.
        """
        self.clear_registers(persistent)
        self.regs.cs.value = cs
        self.mem.ptr = 0
        exitcode = 0
        int_table = len(self.mem)-512
        del persistent
        del cs
        while True:
            self.mem.ptr = self.cs.b+self.ip.b
            if 'bp' in self.__dict__ and self.bp == self.mem.ptr: break
            self.device_cycle()
            op = self.mem.read().b
            if 'stepping' in self.__dict__ and op > 0:
                for reg in self.regs.registers:
                    sys.stdout.write('%s=%s\t' % (reg.upper(), getattr(self.regs, reg).b))
                sys.stdout.write('\n')
            if op == 1:
                i = self.mem.read().b
                if i > 0: # INT operation/Software interrupt
                    self.ip.value = self.mem.ptr-self.cs.b
                    self.push_registers(['cs','ip'])
                    jmp = self.mem[i*2+int_table:i*2+int_table+2].b
                    self.regs.cs.value = jmp
                    self.ip.value = 0
                else: # RET operation/Return from an INT or CALL.
                    self.pop_registers(['ip','cs'])
                continue
            elif op == 2: # MOV operation/Memory moving
                xop,dst,src = self.get_xop()
                if xop.bit(0):
                    self.mem[self.ds.b+dst] = src
                elif xop.bit(1):
                    dst = getattr(self, self.var_map[dst])
                    dst.value = src
                else:
                    raise CPUException('Attempted to move data into immediate value.')
            elif op == 3: # IN operation/Standard I/O
                v = self.mem.read16().b
                port = self.mem.read16().b
                if self.cpu_hooks.has_key(port):
                    getattr(self, self.var_map[v]).value = self.cpu_hooks[port].input(port)
            elif op == 4: # OUT operation/Standard I/O
                port = self.mem.read16().b
                v = self.mem.read16().b
                if self.cpu_hooks.has_key(port):
                    self.cpu_hooks[port].output(port, getattr(self, self.var_map[v]).b)
            elif op == 5: # HLT operation/Halts the CPU
                exitcode = self.mem.read().b
                break
            elif op == 6: # JMP operation
                jmp = self.mem.read16()
                self.mem.ptr = jmp.b+self.cs.b
            elif op == 7: # PUSH operation/Pushes a register onto the stack
                v = self.mem.read().b
                if v > 0:
                    src = getattr(self, self.var_map[v])
                    self.mem[self.ss.b+self.sp.b] = src
                    self.sp.value += 2
                else:
                    self.push_registers()
            elif op == 8: # POP operation/Pops a register off the stack
                v = self.mem.read().b
                if v > 0:
                    self.sp.value -= 2
                    src = self.mem[self.ss.b+self.sp.b:self.ss.b+self.sp.b+2].b
                    getattr(self, self.var_map[v]).value = src
                else:
                    self.pop_registers()
            elif op == 9: # CALL operation/Jumps to an address after pushing the code segment and instruction pointer onto the stack
                jmp = self.mem.read16()
                self.ip.value = self.mem.ptr-self.cs.b
                self.push_registers(['cs','ip'])
                self.mem.ptr = jmp.b+self.cs.b
            elif op == 10: # INC operation/Increments a register by one
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn).b
                reg += 1
                if v > 0:
                    getattr(self, vn).value = reg
                else:
                    raise CPUException('Program attempted to change IP.')
            elif op == 11: # DEC operation/Decreases a register by one
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn).b
                reg -= 1
                if v > 0:
                    getattr(self, vn).value = reg
                else:
                    raise CPUException('Program attempted to change IP.')
            elif op == 12: # ADD operation/Adds two values
                xop,dst,src = self.get_xop(1, 'ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value += src
            elif op == 13: # SUB operation/Subtracts one value from another
                xop,dst,src = self.get_xop(1, 'ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value -= src
            elif op == 14: # TEST operation
                xop,dst,src = self.get_xop()
                if xop.bit(0):
                    result = src & self.mem[self.ds.b+dst].b
                elif xop.bit(1):
                    result = src & getattr(self, self.var_map[dst]).b
                else:
                    result = src & dst
                self.flags.bit(0, True if result == 0 else False)
            elif op == 15: # JE operation
                jmp = self.mem.read16().b
                if self.flags.bit(0):
                    self.mem.ptr = self.cs.b+jmp
            elif op == 16: # JNE operation
                jmp = self.mem.read16().b
                if not self.flags.bit(0):
                    self.mem.ptr = self.cs.b+jmp
            elif op == 17: # CMP operation/Compares two values
                xop,dst,src = self.get_xop()
                if xop.bit(0):
                    result = src - self.mem[self.ds.b+dst].b
                elif xop.bit(1):
                    result = src - getattr(self, self.var_map[dst]).b
                else:
                    result = src - dst
                self.flags.bit(0, True if result == 0 else False)
            elif op == 18: # MUL operation/Multiplies two values together
                xop,dst,src = self.get_xop(1, 'ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value *= src
            elif op == 19: # DIV operation/Divides two values
                xop,dst,src = self.get_xop(1, 'ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value /= src
            elif op == 20: # PUSHF operation pushes FLAGS to stack
                self.push_value(self.flags.b)
            elif op == 21: # POPF operation pops FLAGS from the stack
                self.flags.value = self.pop_value()
            elif op == 22: # AND operation
                xop,dst,src = self.get_xop(1, 'AND operation excepts the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value = dst.value & src
            elif op == 23: # OR operation
                xop,dst,src = self.get_xop(1, 'OR operation excepts the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value = dst.value | src
            elif op == 24: # XOR operation
                xop,dst,src = self.get_xop(1, 'XOR operation excepts the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value = dst.value ^ src
            elif op == 25: # NOT operation
                xop,dst,src = self.get_xop(1, 'NOT operation excepts the destination to be a register.')
                dst = getattr(self, self.var_map[dst])
                dst.value = dst.value & ~src
            self.ip.value = self.mem.ptr-self.cs.b
        self.stop_devices()
        self.mem.offset = 0
        return exitcode
    def loadbin(self, filename, dest, compressed=False):
        if not compressed:
            bindata = open(filename, 'rb').read()
        else:
            bindata = zlib.decompress(open(filename, 'rb').read())
        self.mem.writeblock(dest, bindata)
        self.mem.ptr = 0
    def savebin(self, filename, src, size, compress=False):
        if not compress:
            open(filename, 'wb').write(self.mem.readblock(src, size))
        else:
            open(filename, 'wb').write(zlib.compress(self.mem.readblock(src, size)))

def main_old():
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-f', '--filename', dest='filename', help='The binary file to execute in the virtual machine')
    parser.add_option('--cs', '--codeseg', type='int', dest='cs', default=0, help='Set a custom code segment')
    parser.add_option('--ds', '--dataseg', type='int', dest='ds', default=3000, help='Set a custom data segment')
    parser.add_option('--ss', '--stackseg', type='int', dest='ss', default=2900, help='Set a custom stack segment')
    parser.add_option('--it', '--inttable', dest='inttbl', default='interrupt.tbl', help='Use a custom interrupt table')
    parser.add_option('--ib', '--intbin', dest='intbin', default='interrupt.bin', help='Use a custom interrupt binary')
    parser.add_option('--iba', '--intaddr', type='int', dest='intaddr', default=1000, help='Set a custom address for the interrupt binary')
    parser.add_option('-i', '--integer', type='int', dest='integer', help='Place an integer onto the stack')
    parser.add_option('-s', '--string', dest='string', help='Please a zero terminated string into the data segment')
    options, args = parser.parse_args()
    del args
    c = CPU()
    if options.filename is None:
        options.cli = True
    else:
        c.loadbin(options.filename, options.cs)
    c.loadbin(options.inttbl, len(c.mem)-512)
    c.loadbin(options.intbin, options.intaddr)
    c.add_device(ConIOHook)
    c.ds.value = options.ds
    c.ss.value = options.ss
    if options.integer:
        c.mem[c.ss.b] = UInt16(options.integer)
        c.sp.value = 2
    if options.string:
        c.mem.ptr = c.ds.b
        c.mem.write(options.string+chr(0))
        c.mem[c.ss.b] = UInt16(0)
        c.sp.value = 2
    try:
        c.run(options.cs, ['ds', 'ss', 'sp'])
    except CPUException, e:
        print e

def main():
    from optparse import OptionParser
    parser = OptionParser()
    options, args = parser.parse_args()
    if len(args) == 0:
        sys.stderr.write('Invalid amount of arguments!\n')
        sys.exit(1)
    c = CPU()
    c.add_device(HelloWorldHook)
    c.loadbin(args[0], 0x0)
    try:
        c.run()
    except CPUException, e:
        sys.stderr.write('%s\n' % e)

if __name__ == '__main__':
    main()