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
        self._offset_stack = []
        self._ptr = 0
        self._offset = 0
    def clear(self):
        self.mem.seek(0)
        self.mem.write('\x00' * self.size)
        self.mem.seek(0)
        self._ptr_stack = []
        self._offset_stack = []
        self._ptr = 0
        self._offset = 0
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
        value = UInt8(self.mem.read(1))
        self.mem.seek(self._ptr)
        return UInt8(value)
    def __setitem__(self, key, value):
        self.__check_key(key)
        self.mem.seek(key)
        self.write(UInt8(value).c)
        self.mem.seek(self._ptr)
    @property
    def ptr(self):
        return self.mem.tell()-self.offset
    @ptr.setter
    def ptr(self, value):
        if not isinstance(value, int):
            raise TypeError
        if value < 0 or value > self.size-1:
            raise CPUException('Memory out of range.')
        self.mem.seek(value+self.offset)
    def push(self):
        self._ptr_stack.append(self.ptr)
    def pop(self):
        self.ptr = self._ptr_stack.pop()
    @property
    def offset(self):
        return self._offset
    @offset.setter
    def offset(self, value):
        if value > 0:
            self._offset_stack.append(self._offset)
            self._offset = value
        else:
            try:
                self._offset = self._offset_stack.pop()
            except:
                self._offset = 0
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
        'jmp': 6,
        'call': 9,
        'if=': 15,
        'if!': 16,
        'sys': 20,
    }
    bc_map = {
        'int': [1,0],
        'push': [7,0],
        'pop': [8,0],
        'inc': [10,3],
        'dec': [11,3],
        'use': [14,3],
    }
    bc2_map = {
        'mov': 2,
        'add': 12,
        'sub': 13,
        'swp': 17,
        'mul': 18,
        'div': 19,
    }
    var_map = {
        'ptr': 0,
        'ax': 1,
        'bx': 2,
        'cx': 3,
        'dx': 4,
    }
    prompt = '0 '
    def configure(self, cpu):
        if not isinstance(cpu, CPU):
            raise TypeError
        self.cpu = cpu
        for hook in self.cpu.cpu_hooks:
            self.bc_map.update({self.cpu.cpu_hooks[hook].opname: [hook,0]})
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
        if self.cpu.mem.offset > 0:
            self.cpu.mem.offset = 0
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
    def do_offset(self, args):
        """ Sets the address translation offset. """
        if args != '':
            self.cpu.mem.offset = int(args)
        else:
            print self.cpu.mem.offset
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
        self.stdout.write('AX=%s, BX=%s, CX=%s, DX=%s\n' % (self.cpu.ax.b, self.cpu.bx.b, self.cpu.cx.b, self.cpu.dx.b))
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
    def __call__(self, i):
        try:
            func = getattr(self, "hook_%d" % i)
        except AttributeError:
            raise InvalidInterrupt("HOOK %d is not defined." % i)
        func()
    def cleanup(self):
        pass

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

class CPUInterrupts(object):
    """
    This class is a Mixin to include the main CPU interrupts
    """
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
            raise CPUException("CPU: Single key input not supported on this platform.")
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

class CPUCore(object):
    ax = UInt16()
    bx = UInt16()
    cx = UInt16()
    dx = UInt16()
    var_map = {
        0: 'ptr',
        1: 'ax',
        2: 'bx',
        3: 'cx',
        4: 'dx',
    }
    def add_cpu_hook(self, klass):
        hook = klass(self)
        self.cpu_hooks.update({hook.opcode: hook})
    def hook_cleanup(self):
        for hook in self.cpu_hooks:
            self.cpu_hooks[hook].cleanup()
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
            src = self.mem[src].b
        return xop,dst,src
    def run(self, ptr=0):
        self.mem.offset = ptr
        self.mem.ptr = 0
        exitcode = 0
        stack = []
        if termios:
            attr = termios.tcgetattr(sys.stdin)
            oldattr = attr[3]
            attr[3] = attr[3] & ~termios.ICANON
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attr)
        while True:
            if 'bp' in self.__dict__ and self.bp == self.mem.ptr: break
            if self.mem.eom: break
            op = self.mem.read().b
            if 'stepping' in self.__dict__ and op > 0:
                print "PTR: %s, OP: %s, AX: %s, BX: %s, CX: %s, DX: %s" % (self.mem.ptr, op, self.ax.b, self.bx.b, self.cx.b, self.dx.b)
            if op == 1:
                rt = self.do_int(self.mem.read().b)
                if rt == 1:
                    self.mem.offset = 0
                    if self.mem.offset == 0:
                        exitcode = self.ax.b
                        break
                    self.mem.ptr = stack.pop()
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
                    self.mem[dst] = src
                else:
                    # Moves data into register.
                    dst.value = src
            elif op == 6:
                jmp = self.mem.read16()
                self.mem.ptr = jmp.b
            elif op == 7:
                v = self.mem.read().b
                if v > 0:
                    stack.append(getattr(self, self.var_map[v]).b)
                else:
                    stack.append(self.mem.ptr)
            elif op == 8:
                v = self.mem.read().b
                if v > 0:
                    getattr(self, self.var_map[v]).value = stack.pop()
                else:
                    self.mem.ptr = stack.pop()
            elif op == 9:
                jmp = self.mem.read16()
                stack.append(self.mem.ptr)
                self.mem.ptr = jmp.b
            elif op == 10:
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn).b
                reg += 1
                if v > 0:
                    getattr(self, vn).value = reg
                else:
                    self.mem.ptr = reg
            elif op == 11:
                v = self.mem.read().b
                vn = self.var_map[v]
                reg = getattr(self, vn).b
                reg -= 1
                if v > 0:
                    getattr(self, vn).value = reg
                else:
                    self.mem.ptr = reg
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
                    self.mem.ptr = reg.b
            elif op == 15:
                if self.cx.b == self.mem.read16().b:
                    self.mem.ptr = self.dx.b
            elif op == 16:
                if self.cx.b != self.mem.read16().b:
                    self.mem.ptr = self.dx.b
            elif op == 17:
                xop,dst,src = self.get_xop(False)
                if xop not in [1,3,6,9]:
                    raise CPUException('SWP operation expects the destination to be a register.')
                if xop in [1,4]:
                    raise CPUException('Cannot use SWP operation on literal integer.')
                # Register is destination
                dst = getattr(self, self.var_map[dst])
                dv = dst.b
                ds = src.b
                src.value = dv
                print xop
                if xop == 9:
                    # Moves memory address into register.
                    dst.value = ds
                    self.mem[ds] = dv
                elif xop == 4:
                    # Moves data in memory address.
                    self.mem[dv] = ds
                else:
                    # Moves data into register.
                    dst.value = ds
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
            elif op == 20:
                jmp = self.mem.read16()
                stack.append(self.mem.ptr)
                self.mem.offset = jmp.b
                self.mem.ptr = 0
            elif self.cpu_hooks.has_key(op):
                self.cpu_hooks[op](self.mem.read().b)
        if termios:
            attr[3] = oldattr
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attr)
        self.hook_cleanup()
        self.mem.offset = 0
        return exitcode

class CPU(CPUCore, CPUInterrupts):
    cpu_memory = 4096
    storage = 4096
    shared_memory = 1024
    def __init__(self, filename=None, compressed=False):
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
    c.add_cpu_hook(BinLoaderHook)
    cli = Coder()
    cli.configure(c)
    cli.cmdloop()
