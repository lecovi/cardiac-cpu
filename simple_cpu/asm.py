from cmd import Cmd
from simple_cpu.cpu import CPU, CPUException, UInt16
import shlex, readline, os, sys
from simple_cpu.devices import ConIOHook, HelloWorldHook
try:
    from simple_cpu.framebuffer import VGAConsoleDevice
except ImportError:
    VGAConsoleDevice = None

class Coder(Cmd):
    """
    This is the new-style Coder class, it uses the standard Python Cmd module to create an easy to use assembler.
    The following dictionary maps here control the bytecodes which are written to memory during the assembly process.
    bc16_map is for bytecodes that support one or two 16-bit integers as parameters.
    bc_map is for bytecodes that only support 8-bit integers, and a single parameter.
    bc2_map is for bytecodes that support complex parameter types and require extra metadata to function at runtime.
    bc0_map is for simple bytecodes that don't take any parameters at all.
    """
    bc16_map = {
        'in': 3,
        'out': 4,
        'jmp': 6,
        'call': 9,
        'je': 15,
        'jne': 16,
    }
    bcX_map = {
        'int': [1,0],
        'ret': [1,0],
        'hlt': [5,0],
        'push': [7,0],
        'pop': [8,0],
        'inc': [10,3],
        'dec': [11,3],
    }
    bc2_map = {
        'mov': 2,
        'add': 12,
        'sub': 13,
        'test': 14,
        'cmp': 17,
        'mul': 18,
        'div': 19,
        'and': 22,
        'or': 23,
        'xor': 24,
        'not': 25,
    }
    bc0_map = {
        'pushf': 20,
        'popf': 21,
    }
    bc_map = {
        'int':  0x1,
        'mov':  0x2,
        'in':   0x3,
        'out':  0x4,
        'hlt':  0x5,
        'jmp':  0x6,
        'push': 0x7,
        'pop':  0x8,
        'call': 0x9,
        'inc':  0xa,
        'dec':  0xb,
        'add':  0xc,
        'sub':  0xd,
        'test': 0xe,
        'je':   0xf,
        'jne':  0x10,
        'cmp':  0x11,
        'mul':  0x12,
        'div':  0x13,
        'pushf':0x14,
        'popf': 0x15,
        'and':  0x16,
        'or':   0x17,
        'xor':  0x18,
        'not':  0x19,
        'ret':  0x1a,
    }
    mov_map = {
        'ax':   0xa0,
        'bx':   0xa1,
        'cx':   0xa2,
        'dx':   0xa3,
    }
    prompt = '0x0 '
    intro = 'Simple CPU Assembler v0.5'
    @property
    def var_map(self):
        """ This is a basic helper property for mapping registers. """
        _var_map = getattr(self, '_var_map', None)
        if _var_map is None:
            regs = self.cpu.var_map
            _var_map = dict([(reg,regs.index(reg)) for reg in regs])
            self._var_map = _var_map
        return _var_map
    @property
    def ptr(self):
        return self.cpu.ip.b
    @ptr.setter
    def ptr(self, value):
        self.cpu.ip.value = value
    def configure(self, cpu):
        """ 
        This needs to be called before running cmdloop, as it configures some special options,
        this may be either moved into __init__ in the future.
        """
        if not isinstance(cpu, CPU):
            raise TypeError
        self.cpu = cpu
        self.labels = {}
        self.cseg = 0
    def unknown_command(self, line):
        self.stdout.write('*** Unknown syntax: %s\n'%line)
    def emptyline(self):
        pass
    def postcmd(self, stop, line):
        self.ptr = self.cpu.mem.ptr
        self.prompt = '%s ' % hex(self.ptr)
        return stop
    def onecmd(self, line):
        try:
            return Cmd.onecmd(self, line)
        except CPUException, e:
            self.stdout.write('CPUException: %s\n' % e)
    def get_label(self, lbl, reference=True):
        """ This method is used to translate variables in the assembly code. """
        if lbl[0] == '*':
            label = lbl[1:]
            if reference == False:
                return self.labels[label][0]
            elif label in self.labels:
                self.labels[label][1].append(self.ptr)
                ptr = self.labels[label][0]
            else:
                self.labels[label] = [0,[self.ptr]]
                ptr = 0
            return ptr
        return lbl
    def get_int(self, arg):
        """ This method is used to translate an argument into an integer we can write into memory. """
        if arg.startswith('h'):
            return int(arg[1:], 16)
        elif arg.startswith('*'):
            return self.get_label(arg)
        try:
            return int(arg)
        except:
            return 0
    def write_type(self, typ, value):
        """ This method is used to write specific type information about an integer into memory. """
        b = value&0xf
        self.cpu.mem.write(b|typ<<4)
        if value < 16:
            return
        elif value < 4096:
            self.cpu.mem.write(value>>4)
        else:
            self.cpu.mem.write16(value>>4)
    def write_value(self, value):
        if value in self.var_map:
            self.cpu.mem.write(self.var_map[value])
        elif value.startswith('&'):
            value = self.get_label(value[1:])
            if isinstance(value, str):
                value = int(value[1:], 16)
            if value < 4096:
                self.write_type(4, value)
            elif value < 1048576:
                self.write_type(5, value)
        else:
            value = self.get_int(value)
            if value < 16:
                self.write_type(1, value)
            elif value < 4096:
                self.write_type(2, value)
            elif value < 1048576:
                self.write_type(3, value)
    def default(self, line):
        if line.startswith('#'):
            return False
        if line == '.':
            return True
        s = shlex.split(line)
        op, arg = s[0], ''
        if len(s) > 1:
            try:
                ptr = int(s[0], 16)
                if s[0][:2] != '0x':
                    raise
                self.cpu.mem.ptr = ptr
                op = s[1]
            except:
                arg = s[1]
        if len(s) in [3,4]:
            try:
                ptr, op, arg = int(s[0], 16), s[1], s[2]
                if s[0][:2] != '0x':
                    raise
                self.cpu.mem.ptr = ptr
            except:
                pass
        if op not in self.bc_map:
            self.unknown_command(line)
            return
        self.cpu.mem.write(self.bc_map[op])
        try:
            a1,a2 = arg.split(',')
        except:
            if arg != '':
                self.write_value(arg)
            return
        self.write_value(a2)
        self.write_value(a1)
    def do_shell(self, args):
        """ Executes a Python command. """
        try:
            print eval(args)
        except:
            print sys.exc_info()[1]
    def do_boot(self, args):
        """ Executes the code currently in memory at an optional memory pointer location. """
        if args != '':
            ptr = int(args, 16)
        else:
            ptr = self.ptr
        try:
            rt = self.cpu.run(ptr, ['ds', 'ss'])
            self.stdout.write('Exit Code: %s\n' % rt)
        except CPUException, e:
            print e
    def do_ptr(self, args):
        """ Sets or returns the current pointer location in memory. """
        if args != '':
            args = self.get_label(args, False)
            self.cpu.mem.ptr = self.get_int(args)
        else:
            print self.ptr
    def do_label(self, args):
        """ Sets or prints a list of pointer variables. """
        if args != '':
            if args.startswith('!'):
                self.cseg = 0
            if args in self.labels:
                self.labels[args][0] = self.cpu.mem.ptr-self.cseg
                for ptr in self.labels[args][1]:
                    self.cpu.mem[ptr] = UInt16(self.labels[args][0])
            else:
                self.labels[args] = [self.cpu.mem.ptr-self.cseg, []]
            if args.startswith('!'):
                self.cseg = self.cpu.mem.ptr
        else:
            lbl = []
            for label in self.labels:
                lbl.append('%s=%s' % (label, self.labels[label]))
            self.columnize(lbl)
    def do_reg(self, args):
        """ Sets any CPU register immediately. """
        s = shlex.split(args)
        if len(s) == 2:
            try:
                v = int(s[1])
            except:
                self.stdout.write('Usage: reg ds 400\n')
                return
            if s[0] in self.cpu.regs.registers:
                getattr(self.cpu, s[0]).value = v
            else:
                self.stdout.write('Valid registers: %s' % ', '.join(self.cpu.regs.registers))
        else:
            self.stdout.write('Usage: reg ds 400\n')
    def do_cseg(self, args):
        """ Sets the current code-segment for the pointer label system. """
        if args != '':
            self.cseg = int(args)
        else:
            self.cseg = self.ptr
    def do_savebin(self, args):
        """ Saves the current binary image in memory to disc. """
        s = shlex.split(args)
        if len(s) > 0:
            if len(s) == 1:
                self.cpu.savebin(s[0], 0, self.cpu.mem.ptr)
            else:
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
            data = s[0].replace('\\n', '\n').replace('\\x00', '\x00')
            for c in data:
                self.cpu.mem.write(ord(c))
            self.cpu.mem.write(0)
    def do_poke(self, args):
        """ Stores a raw byte at a specific memory location. """
        if args != '':
            try:
                addr,value = args.split(',')
            except ValueError:
                addr,value = hex(self.ptr), args
            self.cpu.mem.write(int(addr,16), self.get_int(value))
    def do_doke(self, args):
        """ Stores a raw 16-bit integer at a specific memory location. """
        if args != '':
            try:
                addr,value = args.split(',')
            except ValueError:
                addr = hex(self.ptr)
            self.cpu.mem.write16(int(addr,16), self.get_int(value))            
    def do_peek(self, args):
        """ Shows a 8-bit integer from a specific memory location. """
        if args != '':
            value = self.cpu.mem.read(int(args,16))
        else:
            value = self.cpu.mem.read(self.ptr)
        if value > 64:
            self.stdout.write('%s / ' % chr(value))
        self.stdout.write('%s (%s)\n' % (hex(value), value))
    def do_deek(self, args):
        """ Shows a 16-bit integer from a specific memory location. """
        if args != '':
            value = self.cpu.mem.read16(int(args,16))
        else:
            value = self.cpu.mem.read16(self.ptr)
        if value > 64 and value < 129:
            self.stdout.write('%s / ' % chr(value))
        self.stdout.write('%s (%s)\n' % (hex(value), value))
    def do_value(self, args):
        if args == '':
            print self.cpu.get_value()
    def do_hexdump(self, args):
        if args != '':
            try:
                start,stop = args.split(':')
                start,stop = int(start,16),int(stop,16)
            except ValueError:
                start = int(args,16)
                stop = start+16
        else:
            start,stop = self.ptr,self.ptr+16
        ptr = start
        while ptr<stop-1:
            self.stdout.write('%s: ' % hex(ptr))
            for i in range(0,16):
                try:
                    self.stdout.write('%s  ' % hex(self.cpu.mem.read(ptr)))
                except:
                    self.stdout.write('0x0  ')
                ptr+=1
            self.stdout.write('\n')
    def do_hex(self, args):
        """ Convert a decimal number to a hex. """
        if args != '':
            self.stdout.write('%s\n' % hex(int(args)))
    def do_decimal(self, args):
        """ Convert a hexidecimal number to decimal. """
        if args != '':
            self.stdout.write('%s\n' % int(args, 16))
    def do_ord(self, args):
        """ Gives the ordinal of a character. """
        if args != '':
            self.stdout.write('%s\n' % ord(args))
    def do_chr(self, args):
        """ Gives the ASCII character of a given ordinal. """
        if args != '':
            value = int(args)
            self.stdout.write('%s (%s)\n' % (hex(value), chr(value)))
    def do_bp(self, args):
        """ Sets a breakpoint at the current memory location. """
        if args != '':
            self.cpu.bp = int(args)
        else:
            self.cpu.bp = self.ptr
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
        """ Changes or views the current memory map. """
        s = shlex.split(args)
        if len(s) != 1:
            self.stdout.write('Current memory map: \n%s\n' % ', '.join(self.cpu.mem.memory_map.keys()))
            return False
    def do_registers(self, args):
        """ Prints the current state of the CPU registers. """
        reglist = []
        for reg in self.cpu.regs.registers:
            reglist.append('%s=%s\t' % (reg.upper(), getattr(self.cpu, reg).b))
        self.columnize(reglist)
    def do_flags(self, args):
        """ Prints the current state of the CPU flags. """
        flaglist = []
        for flag in range(0,7):
            flaglist.append('FLAG%s=%s' % (flag, self.cpu.flags.bit(flag)))
        self.columnize(flaglist)
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

def main():
    from optparse import OptionParser
    parser = OptionParser('%prog -c|-o OUTPUT SOURCE')
    parser.add_option('--source', dest='source', help='Compile source code file into a binary image')
    parser.add_option('-o', '--output', dest='output', help='Specify a filename for the assembled binary image')
    parser.add_option('-c', '--cli', action='store_true', dest='cli', default=False, help='Start the command-line assembler/debugger')
    parser.add_option('--vgaconsole', action='store_true', dest='enable_vga', default=False, help='Enable the VGAConsole framebuffer device')
    options, args = parser.parse_args()
    source = None
    if len(args) > 1:
        parser.error('You can only supply a single source file.')
    if len(args) > 0:
        source = args[0]
    if options.source:
        if source is not None:
            parser.error('You can only supply a single source file.')
        source = options.source
    c = CPU()
    cli = Coder()
    cli.configure(c)
    if source is not None:
        cli.do_source(sys.argv[1])
        cli.cmdqueue.append('.')
        cli.cmdloop('Assembling %s...' % source)
        if options.output:
            fname = options.output
        else:
            fname = '%s.bin' % source.split('.')[0]
        c.savebin(fname, 0, c.mem.ptr)
    elif options.cli:
        c.add_device(ConIOHook)
        c.add_device(HelloWorldHook)
        if options.enable_vga:
            if VGAConsoleDevice:
                c.add_device(VGAConsoleDevice)
            else:
                parser.error('Please download and install VGAConsole from https://bitbucket.org/kveroneau/pygame-vgaconsole/')
        c.start_devices()
        try:
            cli.cmdloop()
        except CPUException, e:
            sys.stderr.write('%s\n' % e)
        finally:
            c.stop_devices()
    else:
        parser.error('Please specify a command-line option.')

if __name__ == '__main__':
    main()
