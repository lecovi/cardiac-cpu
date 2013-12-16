from cStringIO import StringIO
import sys
import zlib
try:
    import termios
except ImportError:
    print "termios not loaded, simulation will be limited."
    termios = None

class Unit(object):
    """
    This klass now has a grand purpose!  It will handle the 6/16-bit value storage transparently.
    """
    def __init__(self, v1=0, v2=0):
        if isinstance(v1, int) and isinstance(v2, int) and v2 > 0:
            object.__setattr__(self, '_value1', v1)
            object.__setattr__(self, '_value2', v2)
        else:
            self.value = v1
    def __setattr__(self, name, value):
        if name == 'value':
            if isinstance(value, str):
                value = ord(value)
            if isinstance(value, int):
                if value > 65535 or value < 0:
                    raise ValueError
                if value < 256:
                    # Set an 8-bit value.
                    object.__setattr__(self, '_value1', value)
                    object.__setattr__(self, '_value2', 0)
                else:
                    # Set a 16-bit value.
                    object.__setattr__(self, '_value1', value-int(value/256)*256)
                    object.__setattr__(self, '_value2', int(value/256))
            else:
                raise TypeError
    def __add__(self, other):
        if isinstance(other, int):
            return Unit(self.w + other)
        elif isinstance(other, Unit):
            return Unit(self.w + other.w)
        else:
            raise NotImplemented
    def __sub__(self, other):
        if isinstance(other, int):
            return Unit(self.w - other)
        elif isinstance(other, Unit):
            return Unit(self.w - other.w)
        else:
            raise NotImplemented
    def __eq__(self, other):
        if isinstance(other, int) and self.w == other:
            return True
        elif isinstance(other, Unit) and self.w == other.w:
            return True
        else:
            return False
    def __ne__(self, other):
        if isinstance(other, int) and self.w != other:
            return True
        elif isinstance(other, Unit) and self.w != other.w:
            return True
        else:
            return False
    @property
    def b(self):
        """Get the byte value."""
        return self._value1
    @property
    def c(self):
        """Get the ascii value."""
        if self._value2 > 0:
            return chr(self._value1)+chr(self._value2)
        return chr(self._value1)
    @property
    def w(self):
        """Get the 16-bit integer value."""
        return self._value2*256+self._value1

class Memory(object):
    def __init__(self, size):
        self.mem = StringIO()
        self.size = size
        self.clear()
    def clear(self):
        self.mem.seek(0)
        self.mem.write('\x00' * self.size)
        self.mem.seek(0)
        self._ptr = 0
    def __len__(self):
        return self.size
    def __check_key(self, key):
        if not isinstance(key, int):
            raise TypeError
        if key < 0 or key > self.size-1:
            raise IndexError
        self._ptr = self.ptr
    def __getitem__(self, key):
        self.__check_key(key)
        self.mem.seek(key)
        value = self.mem.read(1)
        self.mem.seek(self._ptr)
        return Unit(value)
    def __setitem__(self, key, value):
        self.__check_key(key)
        self.mem.seek(key)
        self.write(value)
        self.mem.seek(self._ptr)
    @property
    def ptr(self):
        return self.mem.tell()
    @ptr.setter
    def ptr(self, value):
        if not isinstance(value, int):
            raise TypeError
        if value < 0 or value > self.size-1:
            raise ValueError
        self.mem.seek(value)
    def read(self, num=1):
        if self.eom:
            print "Memory error: %d" % self.ptr
        if num == 1:
            return Unit(self.mem.read(1))
        return self.mem.read(num)
    def read16(self):
        if self.eom:
            print "Memory error: %d" % self.ptr
        return Unit(ord(self.mem.read(1)), ord(self.mem.read(1)))
    def write(self, value):
        if isinstance(value, Unit):
            self.mem.write(value.c)
        elif isinstance(value, int):
            self.mem.write(chr(value))
        elif isinstance(value, str):
            self.mem.write(value)
        else:
            raise ValueError
    def write16(self, value):
        if isinstance(value, Unit):
            self.mem.write(value.c)
        elif isinstance(value, int):
            self.mem.write(Unit(value).c)
        elif isinstance(value, str):
            self.mem.write(value)
        else:
            raise ValueError
    def readstring(self, term='\x00'):
        s = ''
        while True:
            if self.ptr > self.size-1: break
            c = self.mem.read(1)
            if c == term: break
            s += c
        return s
    @property
    def eom(self):
        return self.ptr > self.size-1
    def memcopy(self, src, dest, size):
        self._ptr = self.ptr
        self.mem.seek(src)
        buf = self.mem.read(size)
        self.mem.seek(dest)
        self.mem.write(buf)
        self.mem.seek(self._ptr)
    def memclear(self, src, size):
        self._ptr = self.ptr
        self.mem.seek(src)
        self.mem.write('\x00' * size)
        self.mem.seek(self._ptr)

class Storage(Memory):
    def __init__(self, filename, size):
        self.size = size
        try:
            self.mem = open(filename, 'r+b')
        except IOError:
            self.mem = open(filename, 'w+b')
            self.clear()

class Coder(object):
    bc_map = {
        'int': 1,
        'ax': 2,
        'bx': 3,
        'cx': 4,
        'dx': 5,
        'jmp': 6,
        'push': 7,
        'pop': 8,
        'call': 9,
        'cx++': 10,
        'cx--': 11,
        'addcx': 12,
        'subcx': 13,
        'use': 14,
        'if=': 15,
        'if!': 16,
    }
    def __init__(self, cpu, compress=False):
        if not isinstance(cpu, CPU):
            raise TypeError
        self.cpu = cpu
        self.compress = compress
        for hook in self.cpu.cpu_hooks:
            self.bc_map.update({self.cpu.cpu_hooks[hook].opname: hook})
    def parse(self, c):
        try:
            sp = c.index(' ')
            return (c[0:sp], c[sp+1:])
        except ValueError:
            return (c, '')
    def __call__(self):
        while True:
            op, arg = self.parse(raw_input("%d " % self.cpu.mem.ptr))
            if op in self.bc_map:
                self.cpu.mem.write(self.bc_map[op])
                if arg != '':
                    self.cpu.mem.write(int(arg))
            elif op == 'boot':
                if arg != '':
                    self.cpu.run(int(arg))
                else:
                    self.cpu.run(self.cpu.mem.ptr)
            elif op == 'string':
                for c in arg:
                    self.cpu.mem.write(2)
                    self.cpu.mem.write(ord(c))
                    self.cpu.mem.write(1)
                    self.cpu.mem.write(3)
            elif op == 'ptr':
                if arg != '':
                    self.cpu.mem.ptr = int(arg)
                else:
                    print self.cpu.mem.ptr
            elif op == 'dump':
                if arg != '':
                    ptr = int(arg)
                else:
                    ptr = self.cpu.mem.ptr
                print self.cpu.mem[ptr].b
            elif op == 'dump+':
                print self.cpu.mem.read().b
            elif op == 'savebin':
                if arg != '':
                    self.cpu.savebin(arg, self.compress)
            elif op == 'loadbin':
                if arg != '':
                    self.cpu.loadbin(arg, self.compress)
            elif op == 'clear':
                self.cpu.mem.clear()
            elif op == 'data':
                for c in arg:
                    self.cpu.mem.write(ord(c))
                self.cpu.mem.write(0)
            elif op == 'set':
                if arg != '':
                    self.cpu.mem.write(int(arg))
            elif op == 'bp':
                if arg != '':
                    self.cpu.bp = int(arg)
                else:
                    self.cpu.bp = self.cpu.mem.ptr
            elif op == 'cbp':
                del self.cpu.bp
            elif op == '.' or self.cpu.mem.eom:
                break
        self.cpu.savebin('dump', self.compress)

class BaseCPUHook(object):
    def __init__(self, cpu):
        if not isinstance(cpu, CPU):
            raise TypeError
        self.cpu = cpu
    def __call__(self, i):
        try:
            func = getattr(self, "hook_%d" % i)
        except AttributeError:
            raise InvalidInterrupt("HOOK %d is not defined." % i)
        func()

class HelloWorldHook(BaseCPUHook):
    opcode = 60
    opname = 'hlo'
    def hook_32(self):
        print "Hello World!"
    def hook_33(self):
        print "Current Register values:"
        print self.cpu.ax.b
        print self.cpu.bx.b
        print self.cpu.cx.b
        print self.cpu.dx.b

class BinLoaderHook(BaseCPUHook):
    """
    BinLoaderHook can be used during development to load binary data directly into an attached storage unit.
    It can also export data from the storage unit directly into an external file.
    """
    opcode = 240
    opname = 'ldr'
    def get_filename(self):
        ptr = self.cpu.mem.ptr
        self.cpu.mem.ptr = self.cpu.ax.b
        filename = self.cpu.mem.readstring()
        self.cpu.mem.ptr = ptr
        return filename
    def hook_10(self):
        self.cpu.storage.write(open(self.get_filename(), 'rb').read())
    def hook_11(self):
        open(self.get_filename(), 'rb').write(self.cpu.storage.read(self.cpu.cx.b))

class InvalidInterrupt(Exception):
    pass

class CPU(object):
    ax = Unit()
    bx = Unit()
    cx = Unit()
    dx = Unit()
    def __init__(self, filename=None, compressed=False):
        self.mem = Memory(64)
        self.storage = Storage('storage', 4096)
        self.imem = Memory(1024)
        self.cpu_hooks = {}
        if filename != None:
            self.loadbin(filename, compressed=compressed)
    def loadbin(self, filename, compressed=False):
        self.mem.clear()
        if not compressed:
            self.mem.write(open(filename, 'rb').read())
        else:
            self.mem.write(zlib.decompress(open(filename, 'rb').read()))
        self.mem.ptr = 0
    def savebin(self, filename, compress=False):
        if not compress:
            open(filename, 'wb').write(self.mem.mem.getvalue())
        else:
            open(filename, 'wb').write(zlib.compress(self.mem.mem.getvalue()))
    def add_cpu_hook(self, klass):
        hook = klass(self)
        self.cpu_hooks.update({hook.opcode: hook})
    def dump(self):
        self.mem.ptr = 0
        for i in range(0, (len(self.mem)/2)-1):
            print "%d, %d" % (self.mem.read().b, self.mem.read().b)
    def do_int(self, i):
        if i == 1:
            return 1
        try:
            func = getattr(self, "int_%d" % i)
        except AttributeError:
            raise InvalidInterrupt("INT %d is not defined." % i)
        func()
    def int_2(self):
        sys.stdout.write('\033[2J\033[0;0H')
    def int_3(self):
        sys.stdout.write("%s" % self.ax.c)
    def int_4(self):
        sys.stdout.write('\033[1;%dm' % self.ax.b)
    def int_5(self):
        self.mem.memcopy(self.ax.b, self.bx.b, self.cx.b)
    def int_6(self):
        self.mem.memclear(self.ax.b, self.cx.b)
    def int_7(self):
        self.storage.ptr = self.ax.b
    def int_8(self):
        ptr = self.mem.ptr
        self.mem.ptr = self.ax.b
        self.mem.write(self.storage.read(self.cx.b))
        self.mem.ptr = ptr
    def int_9(self):
        ptr = self.mem.ptr
        self.mem.ptr = self.ax.b
        self.storage.write(self.mem.read(self.cx.b))
        self.mem.ptr = ptr
    def int_10(self):
        ptr = self.mem.ptr
        self.mem.ptr = self.ax.b
        sys.stdout.write(self.mem.readstring())
        self.mem.ptr = ptr
    def int_11(self):
        if termios:
            sys.stdin.flush()
            self.mem[self.cx.b] = sys.stdin.read(1)
        else:
            print "CPU: Single key input not supported on this platform."
            self.mem[self.cx.b] = 'A'
    def int_12(self):
        ptr = self.mem.ptr
        self.mem.ptr = self.ax.b
        s = raw_input()
        for c in s:
            self.mem.write(ord(c))
        self.mem.write(0)
        self.cx.value = len(s)
        self.mem.ptr = ptr
    def int_40(self):
        ptr = self.mem.ptr
        self.mem.ptr = self.ax.b
        self.imem.ptr = self.bx.b
        self.imem.write(self.mem.read(self.cx.b))
        self.mem.memclear(self.ax.b, self.cx.b)
        self.mem.ptr = ptr
    def int_41(self):
        ptr = self.mem.ptr
        self.imem.ptr = self.ax.b
        self.mem.ptr = self.bx.b
        self.mem.write(self.imem.read(self.cx.b))
        self.imem.memclear(self.ax.b, self.cx.b)
        self.mem.ptr = ptr
    def int_42(self):
        self.imem.ptr = self.ax.b
        self.storage.write(self.imem.read(self.cx.b))
    def int_43(self):
        self.imem.ptr = self.ax.b
        self.imem.write(self.storage.read(self.cx.b))
    def int_255(self):
        self.savebin('dump')
        cli = Coder(self)
        cli()
    def run(self, ptr=0):
        self.mem.ptr = ptr
        exitcode = 0
        sjmp = ptr
        if termios:
            attr = termios.tcgetattr(sys.stdin)
            oldattr = attr[3]
            attr[3] = attr[3] & ~termios.ICANON
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attr)
        while True:
            if 'bp' in self.__dict__ and self.bp == self.mem.ptr: break
            if self.mem.eom: break
            op = self.mem.read().b
            if op == 1:
                rt = self.do_int(self.mem.read().b)
                if rt == 1:
                    exitcode = 1
                    break
            elif op == 2:
                self.ax = self.mem.read()
            elif op == 3:
                self.bx = self.mem.read()
            elif op == 4:
                self.cx = self.mem.read()
            elif op == 5:
                self.dx = self.mem.read()
            elif op == 6:
                jmp = self.mem.read()
                self.mem.ptr = jmp.b
            elif op == 7:
                sjmp = self.mem.ptr
            elif op == 8:
                self.mem.ptr = sjmp
            elif op == 9:
                sjmp = self.mem.ptr + 1
                jmp = self.mem.read()
                self.mem.ptr = jmp.b
            elif op == 10:
                self.cx += 1
            elif op == 11:
                self.cx -= 1
            elif op == 12:
                self.cx += self.mem.read()
            elif op == 13:
                self.cx -= self.mem.read()
            elif op == 14:
                self.cx = self.mem[self.cx.b]
            elif op == 15:
                if self.cx == self.mem.read():
                    self.mem.ptr = self.dx.b
            elif op == 16:
                if self.cx != self.mem.read():
                    self.mem.ptr = self.dx.b
            elif self.cpu_hooks.has_key(op):
                self.cpu_hooks[op](self.mem.read().b)
        if termios:
            attr[3] = oldattr
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attr)

if __name__ == '__main__':
    import readline
    c = CPU('hello.bin', True)
    c.add_cpu_hook(BinLoaderHook)
    cli = Coder(c)
    cli()
