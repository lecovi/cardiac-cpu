import sys, zlib
from simple_cpu.exceptions import CPUException
from simple_cpu.devices import ConIOHook, HelloWorldHook
from simple_cpu.memory import UInt16, UInt8, MemoryController, IOMap, MemoryMap

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
            self.mem.write16(self.ss+self.sp, getattr(self.regs, reg).b)
            self.sp.value += 2
    def pop_registers(self, regs=None):
        if regs is None:
            regs = self.regs.pushable.reverse()
        for reg in regs:
            self.sp.value -= 2
            getattr(self.regs, reg).value = self.mem.read16(self.ss+self.sp)
    def push_value(self, value):
        try:
            value = int(value)
            self.mem.write16(self.ss+self.sp,value)
            self.sp.value += 2
        except:
            self.mem.ptr = self.ds
            self.mem.write(value+chr(0))
            self.mem[self.ss+self.sp] = 0
            self.sp.value += 2
    def pop_value(self):
        if self.sp.value > 0:
            self.sp.value -= 2
            return self.mem.read16(self.ss+self.sp)
        raise CPUException('Stack out of range.')
    def resolve(self, typ, value):
        if typ == 0:
            value = value.b
        elif typ == 4:
            value = self.mem.read(value)
        elif typ == 5:
            value = self.mem.read16(value)
        return value
    def get_value(self, resolve=True):
        b = self.fetch()
        typ = b>>4
        b = b&0xf
        if typ == 0:
            value = getattr(self, self.var_map[b])
        elif typ == 1:
            value = b
        elif typ in (2,4,):
            value = b|self.fetch()<<4
        elif typ in (3,5,):
            value = b|self.fetch16()<<4
        if resolve:
            return typ, self.resolve(typ, value)
        return typ, value
    def set_value(self, dst, src, valid=None):
        if valid is not None and dst[0] not in valid:
            raise CPUException('Attempted to place data in invalid location for specific operation.')
        typ, dst = dst
        if typ == 0:
            dst.value = src
        elif typ in (4,5,):
            if src < 256:
                self.mem[self.ds+dst] = src
            else:
                self.mem.write16(self.ds+dst, src)
        else:
            raise CPUException('Attempted to move data into immediate value.')
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
        """ INT """
        i = self.get_value()[1]
        self.ip.value = self.mem.ptr-self.cs
        self.push_registers(['cs', 'ip'])
        jmp = self.mem[i*2+self.int_table:i*2+self.int_table+2]
        self.regs.cs.value = jmp
        self.ip.value = 0
        return True
    def opcode_0x2(self):
        """ MOV """
        src = self.get_value()[1]
        dst = self.get_value(False)
        self.set_value(dst, src)
    def opcode_0x3(self):
        """ IN """
        src = self.get_value()[1]
        dst = self.get_value(False)
        if self.cpu_hooks.has_key(src):
            self.set_value(dst, self.cpu_hooks[src].input(src))
    def opcode_0x4(self):
        """ OUT """
        src = self.get_value()[1]
        dst = self.get_value()[1]
        if self.cpu_hooks.has_key(dst):
            self.cpu_hooks[dst].output(dst, src)
    def opcode_0x5(self):
        """ HLT """
        self.running = False
    def opcode_0x6(self):
        """ JMP """
        self.mem.ptr = self.cs.b+self.get_value()[1]
    def opcode_0x7(self):
        """ PUSH """
        typ, src = self.get_value()
        if typ == 0:
            self.push_value(src)
        else:
            raise CPUException('Attempt to PUSH a non-register.')
    def opcode_0x8(self):
        """ POP """
        dst = self.get_value(False)
        self.set_value(dst, self.pop_value(), [0])
    def opcode_0x9(self):
        """ CALL """
        jmp = self.cs.b+self.get_value()[1]
        self.ip.value = self.mem.ptr-self.cs.b
        self.push_registers(['cs', 'ip'])
        self.mem.ptr = jmp
    def opcode_0xa(self):
        """ INC """
        typ, src = self.get_value(False)
        if typ == 0:
            src.value +=1
        else:
            raise CPUException('Attempt to increment a non-register.')
    def opcode_0xb(self):
        """ DEC """
        typ, src = self.get_value(False)
        if typ == 0:
            src.value -=1
        else:
            raise CPUException('Attempt to decrement a non-register.')
    def opcode_0xc(self):
        """ ADD """
        src = self.get_value()[1]
        dst = self.get_value(False)
        self.set_value(dst, src+dst[1].b)
    def opcode_0xd(self):
        """ SUB """
        src = self.get_value()[1]
        dst = self.get_value(False)
        self.set_value(dst, dst[1].b-src)
    def opcode_0xe(self):
        """ TEST """
        src = self.get_value()[1]
        dst = self.get_value()[1]
        self.flags.bit(0, src == dst)
    def opcode_0xf(self):
        """ JE """
        jmp = self.get_value()[1]
        if self.flags.bit(0):
            self.mem.ptr = self.cs.b+jmp
    def opcode_0x10(self):
        """ JNE """
        jmp = self.get_value()[1]
        if not self.flags.bit(0):
            self.mem.ptr = self.cs.b+jmp
    def opcode_0x11(self):
        """ CMP """
        src = self.get_value()[1]
        dst = self.get_value()[1]
        result = src - dst
        self.flags.bit(0, True if result == 0 else False)
    def opcode_0x12(self):
        """ MUL """
        src = self.get_value()[1]
        dst = self.get_value(False)
        self.set_value(dst, dst[1].b*src)
    def opcode_0x13(self):
        """ DIV """
        src = self.get_value()[1]
        dst = self.get_value(False)
        self.set_value(dst, dst[1].b/src)
    def opcode_0x14(self):
        """ PUSHF """
        self.push_value(self.flags.b)
    def opcode_0x15(self):
        """ POPF """
        self.flags.value = self.pop_value()
    def opcode_0x16(self):
        """ AND """
        src = self.get_value()[1]
        dst = self.get_value(False)
        v = self.resolve(*dst)
        self.set_value(dst, v & src, [0])
    def opcode_0x17(self):
        """ OR """
        src = self.get_value()[1]
        dst = self.get_value(False)
        v = self.resolve(*dst)
        self.set_value(dst, v | src, [0])
    def opcode_0x18(self):
        """ XOR """
        src = self.get_value()[1]
        dst = self.get_value(False)
        v = self.resolve(*dst)
        self.set_value(dst, v ^ src, [0])
    def opcode_0x19(self):
        """ NOT """
        src = self.get_value()[1]
        dst = self.get_value(False)
        v = self.resolve(*dst)
        self.set_value(dst, v & ~src, [0])
    def opcode_0x1a(self):
        """ RET """
        self.pop_registers(['ip', 'cs'])
        return True
    def run(self, cs=0, persistent=[]):
        self.clear_registers(persistent)
        self.cs.value = cs
        self.mem.ptr = 0
        self.int_table = len(self.mem)-512
        del persistent
        del cs
        self.running = True
        while self.running:
            if 'bp' in self.__dict__ and self.bp == self.mem.ptr: break
            self.device_cycle()
            self.process()
        self.stop_devices()
        return 0
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
    """ Keeping this around until I migrate it over to the new format. """
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
    """ In reality, main() should be application specific. """
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
