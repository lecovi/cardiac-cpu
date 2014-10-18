from cmd import Cmd
from cpu import CPU, UInt8, CPUException, UInt16, Memory, ConIOHook
import shlex, readline, os, sys

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
    bc_map = {
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
    prompt = '0x0 '
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
        self.labels = {}
        self.cseg = 0
    def unknown_command(self, line):
        self.stdout.write('*** Unknown syntax: %s\n'%line)
    def emptyline(self):
        pass
    def postcmd(self, stop, line):
        self.prompt = '%s ' % hex(self.cpu.mem.ptr)
        return stop
    def get_label(self, lbl, reference=True):
        if lbl[0] == '*':
            label = lbl[1:]
            if reference == False:
                return self.labels[lbl[1:]][0]
            elif label in self.labels:
                self.labels[label][1].append(self.cpu.mem.ptr)
                ptr = self.labels[lbl[1:]][0]
            else:
                self.labels[label] = [0,[self.cpu.mem.ptr]]
                ptr = 0
            return ptr
        return lbl
    def get_int(self, arg):
        if arg.startswith('h'):
            return int(arg[1:], 16)
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
        if op in self.bc0_map:
            # This map is for simple operations that don't take any parameters.
            self.cpu.mem.write(self.bc0_map[op])
        elif op in self.bc16_map:
            # This map is for operations which can take a 16-bit integer parameter.
            self.cpu.mem.write(self.bc16_map[op])
            if arg != '':
                if ',' in arg:
                    a1,a2 = arg.split(',')
                    self.cpu.mem.write16(self.get_int(a1))
                    self.cpu.mem.write16(self.get_int(a2))
                else:
                    arg = self.get_label(arg)
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
            xop = UInt8()
            if a1.startswith('&'):
                xop.bit(0, True)
                a1 = a1[1:]
            if a2.startswith('&'):
                xop.bit(2, True)
                a2 = a2[1:]
            if a1 in self.var_map:
                xop.bit(1, True)
                a1 = self.var_map[a1]
            if a2 in self.var_map:
                xop.bit(3, True)
                a2 = self.var_map[a2]
            self.cpu.mem.write(xop)
            if isinstance(a1, str):
                a1 = self.get_label(a1)
                self.cpu.mem.write16(int(a1))
            else:
                self.cpu.mem.write(int(a1))
            if isinstance(a2, str):
                a2 = self.get_label(a2)
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
            print self.cpu.mem.ptr
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
            self.cseg = self.cpu.mem.ptr
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
        """ Changes or views the current memory map. """
        s = shlex.split(args)
        if len(s) != 1:
            self.stdout.write('Current memory map: \n%s\n' % ', '.join(self.cpu.mem.memory_map.keys()))
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
    parser = OptionParser()
    parser.add_option('--source', dest='source', help='Compile source code file into a binary image')
    parser.add_option('--ds', '--dataseg', type='int', dest='ds', default=3000, help='Set a custom data segment')
    parser.add_option('--ss', '--stackseg', type='int', dest='ss', default=2900, help='Set a custom stack segment')
    parser.add_option('--it', '--inttable', dest='inttbl', default='interrupt.tbl', help='Use a custom interrupt table')
    parser.add_option('--ib', '--intbin', dest='intbin', default='interrupt.bin', help='Use a custom interrupt binary')
    parser.add_option('--iba', '--intaddr', type='int', dest='intaddr', default=1000, help='Set a custom address for the interrupt binary')
    parser.add_option('-c', '--cli', action='store_true', dest='cli', default=False, help='Start the command-line assembler/debugger')
    options, args = parser.parse_args()
    del args
    c = CPU()
    c.loadbin(options.inttbl, len(c.mem)-512)
    c.loadbin(options.intbin, options.intaddr)
    c.add_cpu_hook(ConIOHook)
    c.ds.value = options.ds
    c.ss.value = options.ss
    if options.source:
        try:
            source = open(options.source, 'r').readlines()
        except:
            parser.error('Source file not found.')
            sys.exit(1)
        cli = Coder()
        cli.configure(c)
        for line in source:
            cli.cmdqueue.append(line)
        cli.cmdqueue.append('.')
        cli.cmdloop('Assembling %s...' % options.source)
        fname = options.source.split('.')
        c.savebin('%s.bin' % fname[0], 0, c.mem.ptr)
        sys.exit(0)
    elif options.cli:
        cli = Coder()
        cli.configure(c)
        cli.cmdloop()

if __name__ == '__main__':
    main()
