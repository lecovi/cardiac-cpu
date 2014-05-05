from cmd import Cmd
import sys, os, zlib, shlex, mmap, struct
try:
    import termios
except ImportError:
    print "termios not loaded, simulation will be limited."
    termios = None

class CPUException(Exception):
    pass

class InvalidInterrupt(CPUException):
    pass

class Unit(object):
    def __init__(self, default=0):
        self.struct = struct.Struct(self.fmt)
        self.value = default
    @property
    def value(self):
        return self._value
    @value.setter
    def value(self, value):
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
            return self.__class__(self._value + other)
        elif isinstance(other, Unit):
            return self.__class__(self._value + other.b)
        else:
            raise NotImplemented
    def __sub__(self, other):
        if isinstance(other, int):
            return self.__class__(self._value - other)
        elif isinstance(other, Unit):
            return self.__class__(self._value - other.b)
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
        return self.value
    @property
    def c(self):
        return self.struct.pack(self.value)

class UInt8(Unit):
    fmt = 'B'

class UInt16(Unit):
    fmt = 'H'

class UInt32(Unit):
    fmt = 'L'

class Memory(object):
    def __init__(self, size):
        self.mem = mmap.mmap(-1, size)
        self.size = size
        self._ptr_stack = []
        self._ptr = 0
    def clear(self):
        self.mem.seek(0)
        self.mem.write('\x00' * self.size)
        self.mem.seek(0)
        self._ptr_stack = []
        self._ptr = 0
    def __len__(self):
        return self.size
    def __check_key(self, key):
        if not isinstance(key, int):
            raise TypeError('Type %s is not valid here.' % type(key))
        if key < 0 or key > self.size-1:
            raise IndexError
        self._ptr = self.ptr
    def __getitem__(self, key):
        if isinstance(key, slice):
            stop = key.stop
            key = key.start
        else:
            stop = key
        self.__check_key(key)
        self.mem.seek(key)
        if stop > key:
            if stop-key == 2:
                value = UInt16(self.mem.read(2))
            else:
                value = self.mem.read(stop-key)
        else:
            value = UInt8(self.mem.read(1))
        self.mem.seek(self._ptr)
        return value
    def __setitem__(self, key, value):
        self.__check_key(key)
        self.mem.seek(key)
        if isinstance(value, Unit):
            self.write(value.c)
        elif isinstance(value, str):
            self.write(value)
        else:
            self.write(UInt8(value).c)
        self.mem.seek(self._ptr)
    @property
    def ptr(self):
        return self.mem.tell()
    @ptr.setter
    def ptr(self, value):
        if not isinstance(value, int):
            raise TypeError
        if value < 0 or value > self.size-1:
            raise CPUException('Memory out of range.')
        self.mem.seek(value)
    def push(self):
        self._ptr_stack.append(self.ptr)
    def pop(self):
        self.ptr = self._ptr_stack.pop()
    def read(self, num=1):
        if self.eom:
            raise CPUException("Memory error: %d" % self.ptr)
        if num == 1:
            return UInt8(self.mem.read(1))
        return self.mem.read(num)
    def read16(self):
        if self.eom:
            raise CPUException("Memory error: %d" % self.ptr)
        if self.size > 256:
            return UInt16(self.mem.read(2))
        return UInt8(self.mem.read(1))
    def write(self, value):
        if isinstance(value, Unit):
            self.mem.write(value.c)
        elif isinstance(value, int):
            if value < 256:
                self.mem.write(chr(value))
            elif value > 65535:
                self.mem.write(UInt32(value).c)
            else:
                self.mem.write(UInt16(value).c)
        elif isinstance(value, str):
            self.mem.write(value)
        else:
            raise ValueError
    def write16(self, value):
        if self.size > 256:
            self.mem.write(UInt16(value).c)
        else:
            self.mem.write(chr(value))
    def readstring(self, term='\x00'):
        s = ''
        while True:
            if self.ptr > self.size-1: break
            c = self.mem.read_byte()
            if c == term: break
            s += c
        return s
    @property
    def eom(self):
        return self.ptr > self.size-1
    def memcopy(self, src, dest, size):
        self.mem.move(dest, src, size)
    def memclear(self, src, size):
        self._ptr = self.ptr
        self.mem.seek(src)
        self.mem.write('\x00' * size)
        self.mem.seek(self._ptr)

class Storage(Memory):
    def __init__(self, filename, size):
        try:
            self.file = open(filename, 'r+b')
        except IOError:
            self.file = open(filename, 'w+b')
        self.mem = mmap.mmap(self.file.fileno(), 0)
        self.mem.resize(size)
        self._ptr_stack = []
        self._ptr = 0

class Coder(Cmd):
    bc16_map = {
        'in': 3,
        'out': 4,
        'jmp': 6,
        'call': 9,
        'if=': 15,
        'if!': 16,
        'sys': 20,
    }
    bc_map = {
        'int': [1,0],
        'ret': [1,0],
        'hlt': [5,0],
        'push': [7,0],
        'pop': [8,0],
        'inc': [10,3],
        'dec': [11,3],
        'use': [14,3],
    }
    bc2_map = {
        'mov': 2,
        'in': 3,
        'out': 4,
        'add': 12,
        'sub': 13,
        'mul': 18,
        'div': 19,
    }
    prompt = '0 '
    @property
    def var_map(self):
        _var_map = getattr(self, '_var_map', None)
        if _var_map is None:
            regs = self.cpu.var_map
            _var_map = dict([(reg,regs.index(reg)) for reg in regs])
            self._var_map = _var_map
        return _var_map
    def configure(self, cpu):
        if not isinstance(cpu, CPU):
            raise TypeError
        self.cpu = cpu
    def unknown_command(self, line):
        self.stdout.write('*** Unknown syntax: %s\n'%line)
    def emptyline(self):
        pass
    def postcmd(self, stop, line):
        self.prompt = '%s ' % self.cpu.mem.ptr
        return stop
    def get_int(self, arg):
        try:
            return int(arg)
        except:
            pass
        try:
            return self.var_map[arg]
        except:
            return 0
    def default(self, line):
        if line == '.':
            return True
        s = shlex.split(line)
        op, arg = s[0], ''
        if len(s) > 1:
            try:
                ptr = int(s[0])
                self.cpu.mem.ptr = ptr
                op = s[1]
            except:
                arg = s[1]
        if len(s) in [3,4]:
            try:
                ptr, op, arg = int(s[0]), s[1], s[2]
                self.cpu.mem.ptr = ptr
            except:
                pass
        if op in self.bc16_map:
            # This map is for operations which can take a 16-bit integer parameter.
            self.cpu.mem.write(self.bc16_map[op])
            if arg != '':
                if ',' in arg:
                    a1,a2 = arg.split(',')
                    self.cpu.mem.write16(self.get_int(a1))
                    self.cpu.mem.write16(self.get_int(a2))
                else:
                    self.cpu.mem.write16(int(arg))
        elif op in self.bc_map:
            # This map is for operations which can take an 8-bit integer parameter.
            self.cpu.mem.write(self.bc_map[op][0])
            if arg == '':
                self.cpu.mem.write(int(self.bc_map[op][1]))
            else:
                self.cpu.mem.write(self.get_int(arg))
        elif op in self.bc2_map:
            # This map is for complex operations that support mixed parameter types, like the MOV instruction.
            try:
                a1,a2 = arg.split(',')
            except:
                self.unknown_command(line)
                return
            self.cpu.mem.write(self.bc2_map[op])
            xop = 0
            if a1.startswith('&'):
                xop+=4
                a1 = a1[1:]
            if a2.startswith('&'):
                xop+=8
                a2 = a2[1:]
            if a1 in self.var_map:
                xop+=1
                a1 = self.var_map[a1]
            if a2 in self.var_map:
                xop+=2
                a2 = self.var_map[a2]
            if xop in [0,2,8,12,15]:
                self.unknown_command(line)
                return
            self.cpu.mem.write(xop)
            if isinstance(a1, str):
                self.cpu.mem.write16(int(a1))
            else:
                self.cpu.mem.write(int(a1))
            if isinstance(a2, str):
                self.cpu.mem.write16(int(a2))
            else:
                self.cpu.mem.write(int(a2))
        else:
            self.unknown_command(line)
    def do_boot(self, args):
        """ Executes the code currently in memory at an optional memory pointer location. """
        if args != '':
            ptr = int(args)
        else:
            ptr = self.cpu.mem.ptr
        try:
            rt = self.cpu.run(ptr)
            self.stdout.write('Exit Code: %s\n' % rt)
        except CPUException, e:
            print e
    def do_string(self, args):
        """ A macro to write a string to the screen 1 character at a time. """
        s = shlex.split(args)
        for c in s[0]:
            self.cpu.mem.write(2)
            self.cpu.mem.write(1)
            self.cpu.mem.write(ord(c))
            self.cpu.mem.write(1)
            self.cpu.mem.write(3)
    def do_ptr(self, args):
        """ Sets or returns the current pointer location in memory. """
        if args != '':
            self.cpu.mem.ptr = int(args)
        else:
            print self.cpu.mem.ptr
    def do_dump(self, args):
        """ Dumps the byte at the current memory location. """
        if args != '':
            ptr = int(args)
        else:
            ptr = self.cpu.mem.ptr
        byte = self.cpu.mem[ptr]
        self.stdout.write("%s" % byte.b)
        if byte.b > 64:
            self.stdout.write(' / %s' % byte.c)
        self.stdout.write('\n')
    def do_dump16(self, args):
        """ Dumps a 16-bit integer from the current memory location. """
        if args != '':
            optr = self.cpu.mem.ptr
            self.cpu.mem.ptr = int(args)
        self.stdout.write("%s\n" % self.cpu.mem.read16().b)
        if args != '':
            self.cpu.mem.ptr = optr
    def do_savebin(self, args):
        """ Saves the current binary image in memory to disc. """
        s = shlex.split(args)
        if len(s) > 0:
            self.cpu.savebin(s[0], self.cpu.mem.ptr, int(s[1]))
    def do_loadbin(self, args):
        """ Loads a binary image from disc into memory. """
        s = shlex.split(args)
        if len(s) > 0:
            if self.cpu.loadbin(s[0], self.cpu.mem.ptr) == False:
                self.stdout.write('The binary is too large to fit in memory.\n')
    def do_clear(self, args):
        """ Clears the current data in memory. """
        self.cpu.mem.clear()
        readline.clear_history()
    def do_data(self, args):
        """ Stores a zero-terminated string to the current memory address. """
        s = shlex.split(args)
        if len(s) > 0:
            for c in s[0]:
                self.cpu.mem.write(ord(c))
            self.cpu.mem.write(0)
    def do_set(self, args):
        """ Stores a raw byte at the current memory location. """
        if args != '':
            self.cpu.mem.write(int(args))
    def do_bp(self, args):
        """ Sets a breakpoint at the current memory location. """
        if args != '':
            self.cpu.bp = int(args)
        else:
            self.cpu.bp = self.cpu.mem.ptr
    def do_cbp(self, args):
        """ Clears a currently set breakpoint. """
        del self.cpu.bp
    def do_source(self, args):
        """ Loads in a source file. """
        s = shlex.split(args)
        if len(s) != 1:
            self.stdout.write('Please specify a filename to read in.\n')
            return False
        try:
            script = open(s[0], 'r').readlines()
            for line in script:
                self.cmdqueue.append(line)
        except:
            self.stdout.write('Error loading source.\n')
    def do_memory(self, args):
        """ Changes or views the current memory size. """
        s = shlex.split(args)
        if len(s) != 1:
            self.stdout.write('Current memory size: %s\n' % self.cpu.mem.size)
            return False
        try:
            self.cpu.mem = Memory(int(s[0]))
        except:
            self.stdout.write('Please specify a size in bytes.\n')
    def do_registers(self, args):
        """ Prints the current state of the CPU registers. """
        reglist = []
        for reg in self.cpu.regs.registers:
            reglist.append('%s=%s\t' % (reg.upper(), getattr(self.cpu, reg).b))
        self.columnize(reglist)
    def do_memcopy(self, args):
        """ Performs a memory copy operation. """
        s = shlex.split(args)
        if len(s) != 3:
            self.stdout.write('Please specify the following: src, dest, size\n')
            return False
        try:
            self.cpu.mem.memcopy(int(s[0]), int(s[1]), int(s[2]))
        except:
            self.stdout.write('There was an error during the copy operation.\n')
    def do_memclear(self, args):
        """ Clear a specific segment of memory. """
        s = shlex.split(args)
        if len(s) != 2:
            self.stdout.write('Please specify the following: src, size\n')
            return False
        try:
            self.cpu.mem.memclear(int(s[0]), int(s[1]))
        except:
            self.stdout.write('There was an error during the memory clear operation.\n')
    def do_memmove(self, args):
        """ Moves a segment of memory to a new location. """
        s = shlex.split(args)
        if len(s) != 3:
            self.stdout.write('Please specify the following: src, dest, size\n')
            return False
        optr = self.cpu.mem.ptr
        try:
            src = int(s[0])
            dest = int(s[1])
            size = int(s[2])
        except:
            self.stdout.write('Please provide numeric parameters only.\n')
            return False
        try:
            self.cpu.mem.ptr = src
            buf = self.cpu.mem.read(size)
        except:
            self.stdout.write('There was an error during the read operation.\n')
            self.cpu.mem.ptr = optr
            return False
        try:
            self.cpu.mem.memclear(src, size)
        except:
            self.stdout.write('There was an error during the clear operation.\n')
            self.cpu.mem.ptr = src
            self.cpu.mem.write(buf)
            self.cpu.mem.ptr = optr
            return False
        try:
            self.cpu.mem.ptr = dest
            old = self.cpu.mem.read(size)
            self.cpu.mem.ptr = dest
            self.cpu.mem.write(buf)
        except:
            self.stdout.write('There was an error during the write operation.\n')
            self.cpu.mem.ptr = dest
            self.cpu.mem.write(old)
            self.cpu.mem.ptr = src
            self.cpu.mem.write(buf)
            self.cpu.mem.ptr = optr
    def do_stepping(self, args):
        """ Turn on or off register stepping for each command run. """
        if args == 'off':
            del self.cpu.stepping
        else:
            self.cpu.stepping = True
    def do_savecode(self, args):
        """ Save your history of typed commands. """
        s = shlex.split(args)
        if len(s) == 1:
            readline.write_history_file(s[0])
            os.chmod(s[0], 33188)

class BaseCPUHook(object):
    def __init__(self, cpu):
        if not isinstance(cpu, CPU):
            raise TypeError
        self.cpu = cpu
    def get_handler(self, i, d):
        try:
            func = getattr(self, "%s_%d" % (d, i))
        except AttributeError:
            raise InvalidInterrupt("Port %d is not defined." % i)
        return func
    def input(self, i):
        func = self.get_handler(i, 'in')
        return func()
    def output(self, i, v):
        func = self.get_handler(i, 'out')
        func(v)
    def cleanup(self):
        pass

class HelloWorldHook(BaseCPUHook):
    ports = [32,33]
    def out_32(self, addr):
        self.addr = addr
    def in_32(self):
        self.cpu.mem[self.addr] = "Hello World!"
        return self.addr
    def out_33(self, reg):
        sys.stdout.write("%s\n" % getattr(self.cpu, self.cpu.var_map[reg]).b)

class ConIOHook(BaseCPUHook):
    """ This implements a basic tty-based display and keyboard for basic input/output operations from the CPU. """
    ports = [8000, 4000]
    def out_8000(self, reg):
        sys.stdout.write('%s' % chr(reg))
    def in_4000(self):
        if termios:
            sys.stdin.flush()
            return sys.stdin.read(1)
        else:
            raise CPUException("CPU: Single key input not supported on this platform.")

class CPURegisters(object):
    """ This class contains all the CPU registers and manages them. """
    registers = ['ip','ax','bx','cx','dx','sp','bp','si','di','cs','ds','es','ss']
    pushable = ['ip','ax','bx','cx','dx','si','di','cs','ds','es']
    def __init__(self):
        for reg in self.registers:
            setattr(self, reg, UInt16())

class CPUCore(object):
    @property
    def var_map(self):
        return self.regs.registers
    @property
    def cs(self):
        return UInt16(self.regs.cs.value)
    def __getattr__(self, name):
        if name in self.regs.registers:
            return getattr(self.regs, name)
        raise AttributeError("%s isn't here." % name)
    def add_cpu_hook(self, klass):
        hook = klass(self)
        for port in hook.ports:
            self.cpu_hooks.update({port: hook})
    def hook_cleanup(self):
        for hook in self.cpu_hooks:
            self.cpu_hooks[hook].cleanup()
    def clear_registers(self):
        for reg in self.var_map:
            getattr(self.regs, reg).value = 0
    def push_registers(self, regs=None):
        if regs is None:
            regs = self.regs.pushable
        for reg in regs:
            self.mem[self.ss.b+self.sp.b] = getattr(self.regs, reg)
            self.sp.value += 2
    def pop_registers(self, regs=None):
        if regs is None:
            regs = self.regs.pushable.reverse()
        for reg in regs:
            self.sp.value -= 2
            src = self.mem[self.ss.b+self.sp.b:self.ss.b+self.sp.b+2].b
            getattr(self.regs, reg).value = src
    def get_xop(self, trans=True):
        """ This handy function to translate the xop code and return a proper integer from the source. """
        xop = self.mem.read().b
        xop_map = {1:'<BH', 3:'<BB', 4:'<HH', 5:'<BH', 6:'<HB', 7:'<BB', 9:'<BH', 11:'<BB'}
        dst,src = struct.unpack(xop_map[xop], self.mem.read(struct.calcsize(xop_map[xop])))
        if xop in [3,6,7,11]:
            # Register is source.
            src = getattr(self, self.var_map[src]).b
        if xop in [9,11]:
            # Memory address is the source.
            src = self.mem[self.ds.b+src].b
        return xop,dst,src
    def run(self, cs=0):
        self.clear_registers()
        self.regs.cs.value = cs
        self.mem.ptr = 0
        exitcode = 0
        int_table = 4000
        if termios:
            attr = termios.tcgetattr(sys.stdin)
            oldattr = attr[3]
            attr[3] = attr[3] & ~termios.ICANON
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attr)
        while True:
            self.mem.ptr = self.cs.b+self.ip.b
            if 'bp' in self.__dict__ and self.bp == self.mem.ptr: break
            if self.mem.eom: break
            op = self.mem.read().b
            if 'stepping' in self.__dict__ and op > 0:
                for reg in self.regs.registers:
                    sys.stdout.write('%s=%s\t' % (reg.upper(), getattr(self.regs, reg).b))
                sys.stdout.write('\n')
            if op == 1:
                i = self.mem.read().b
                if i > 0:
                    self.ip.value = self.mem.ptr-self.cs.b
                    self.push_registers(['cs','ip'])
                    jmp = self.mem[i*2+int_table:i*2+int_table+2].b
                    self.regs.cs.value = jmp
                    self.ip.value = 0
                else:
                    self.pop_registers(['ip','cs'])
                continue
            elif op == 2:
                xop,dst,src = self.get_xop()
                if xop in [1,3,9,11]:
                    # Register is destination
                    dst = getattr(self, self.var_map[dst])
                elif xop in [5,7]:
                    dst = getattr(self, self.var_map[dst]).b
                if xop in [9,11]:
                    # Moves memory address into register.
                    dst.value = src
                elif xop in [4,5,6,7]:
                    # Moves data in memory address.
                    self.mem[self.ds.b+dst] = src
                else:
                    # Moves data into register.
                    dst.value = src
            elif op == 3:
                v = self.mem.read16().b
                port = self.mem.read16().b
                if self.cpu_hooks.has_key(port):
                    getattr(self, self.var_map[v]).value = self.cpu_hooks[port].input(port)
            elif op == 4:
                port = self.mem.read16().b
                v = self.mem.read16().b
                if self.cpu_hooks.has_key(port):
                    self.cpu_hooks[port].output(port, getattr(self, self.var_map[v]).b)
            elif op == 5:
                exitcode = self.mem.read().b
                break
            elif op == 6:
                jmp = self.mem.read16()
                self.mem.ptr = jmp.b+self.cs.b
            elif op == 7:
                v = self.mem.read().b
                if v > 0:
                    src = getattr(self, self.var_map[v])
                    self.mem[self.ss.b+self.sp.b] = src
                    self.sp.value += 2
                else:
                    self.push_registers()
            elif op == 8:
                v = self.mem.read().b
                if v > 0:
                    src = self.mem[self.ss.b+self.sp.b:self.ss.b+self.sp.b+2].b
                    self.sp.value -= 2
                    getattr(self, self.var_map[v]).value = src
                else:
                    self.pop_registers()
            elif op == 9:
                jmp = self.mem.read16()
                self.mem[self.ss.b+self.sp.b] = self.mem.ptr
                self.mem.ptr = jmp.b+self.cs.b
            elif op == 10:
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn).b
                reg += 1
                if v > 0:
                    getattr(self, vn).value = reg
                else:
                    raise CPUException('Program attempted to change IP.')
            elif op == 11:
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn).b
                reg -= 1
                if v > 0:
                    getattr(self, vn).value = reg
                else:
                    raise CPUException('Program attempted to change IP.')
            elif op == 12:
                xop,dst,src = self.get_xop()
                if xop not in [1,3,6,9,11]:
                    raise CPUException('ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                # Register is destination
                dst = getattr(self, self.var_map[dst])
                dst.value += src
            elif op == 13:
                xop,dst,src = self.get_xop()
                if xop not in [1,3,6,9,11]:
                    raise CPUException('ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                # Register is destination
                dst = getattr(self, self.var_map[dst])
                dst.value -= src
            elif op == 14:
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn)
                reg.value = self.mem[reg.b]
                if v > 0:
                    getattr(self, vn).value = reg.b
                else:
                    raise CPUException('Program attempted to change IP.')
            elif op == 15:
                if self.cx.b == self.mem.read16().b:
                    self.mem.ptr = self.dx.b+self.cs.b
            elif op == 16:
                if self.cx.b != self.mem.read16().b:
                    self.mem.ptr = self.dx.b+self.cs.b
            elif op == 18:
                xop,dst,src = self.get_xop()
                if xop not in [1,3,6,9,11]:
                    raise CPUException('ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                # Register is destination
                dst = getattr(self, self.var_map[dst])
                dst.value *= src
            elif op == 19:
                xop,dst,src = self.get_xop()
                if xop not in [1,3,6,9,11]:
                    raise CPUException('ADD, SUB, MUL, DIV operations expect the destination to be a register.')
                # Register is destination
                dst = getattr(self, self.var_map[dst])
                dst.value /= src
            self.ip.value = self.mem.ptr-self.cs.b
        if termios:
            attr[3] = oldattr
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attr)
        self.hook_cleanup()
        self.mem.offset = 0
        return exitcode

class CPU(CPUCore):
    cpu_memory = 4096
    storage = 4096
    shared_memory = 1024
    def __init__(self, filename=None, compressed=False):
        self.regs = CPURegisters()
        self.mem = Memory(self.cpu_memory)
        self.storage = Storage('storage', self.shared_memory) if self.storage > 0 else None
        self.imem = Memory(self.shared_memory) if self.shared_memory > 0 else None
        self.cpu_hooks = {}
        if filename != None:
            self.loadbin(filename, compressed=compressed)
    def loadbin(self, filename, dest, compressed=False):
        if not compressed:
            bindata = open(filename, 'rb').read()
        else:
            bindata = zlib.decompress(open(filename, 'rb').read())
        self.mem.push()
        self.mem.ptr = dest
        self.mem.write(bindata)
        self.mem.pop()
    def savebin(self, filename, src, size, compress=False):
        self.mem.push()
        self.mem.ptr = src
        if not compress:
            open(filename, 'wb').write(self.mem.mem.read(size))
        else:
            open(filename, 'wb').write(zlib.compress(self.mem.mem.read(size)))
        self.mem.pop()

if __name__ == '__main__':
    import readline
    c = CPU()
    c.loadbin('interrupt.tbl', 4000)
    c.loadbin('int10.bin', 1000)
    c.add_cpu_hook(ConIOHook)
    cli = Coder()
    cli.configure(c)
    cli.cmdloop()
